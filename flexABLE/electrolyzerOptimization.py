import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd
from pyomo.util.infeasible import log_infeasible_constraints
import logging





def elecOptBase(optHorizon,   # klammern alle überprüfen #HERE
                timestampsPreviousSection,
                previousSection = pd.DataFrame(),
                PFC = [],
                minLoad = 0.1, #%
                maxLoad = 1.2, #%
                Capacity = 100, #[MW] installed capacity
                effElec = 0.7, #electrolyzer efficiency[%]
                minDownTime  = 2, #minimum downtime,
                coldStartUpCost = 50, # Euro per MW installed capacity,
                maxAllowedColdStartups = 3000, #yearly allowed max cold startups,
                standbyCons = 0.05, #% of installed capacity 
                comprCons = 0.0012, #MWh/kg  compressor specific consumptin
                maxSOC = 2000, #Kg
                industry_demand = [],
                slagCost = 100000):
    
    logging.debug("--------------Start Optimization Electrolyzer-----------------")

    

    energyContentH2_LHV = 0.03333 #MWh/kg or lower heating value of H2
    minPower = Capacity * minLoad #[MW]
    maxPower = Capacity * maxLoad
    standbyCons = standbyCons * Capacity
    coldStartUpCost = coldStartUpCost*Capacity
 
       
    # 1. Define the model, sets, and parameters ----------------------------------------------------------------------------

    # 1.1. create the model

   
    
    model = pyo.ConcreteModel()
    TPrevious = timestampsPreviousSection # number of timesteps of previous section to consider
    
    el_PFC = PFC # assumed production cost = PFC


    
    model.timesteps = pyo.RangeSet(1, optHorizon+TPrevious)

    # Define the decision variables
    model.bidQuantity_MW = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals)
    model.prodH2_kg = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #produced H2
    model.elecCons_MW = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #electrolyzer consumption per kg
    model.elecStandByCons_MW = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #electrolyzer consumption per kg
    # model.elecColdStartUpCons_MW = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #electrolyzer cold startup consumption per kg
    model.elecColdStartUpCost_EUR = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #electrolyzer consumption per kg
    model.comprCons_MW = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #compressor consumption per kg
    model.elecToStorage_kg = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #H2 from electrolyzer to storage
    model.elecToPlantUse_kg = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #H2 from electrolyzer to process
    model.storageToPlantUse_kg = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #H2 from storage to process
    model.currentSOC_kg = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #Status of Storage
    model.slag = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) #Slack variable

    # Binary variable to represent the status of the electrolyzer (on/off)
    model.isRunning = pyo.Var(model.timesteps, domain=pyo.Binary, doc='Electrolyzer running')
    model.isColdStarted = pyo.Var(model.timesteps, domain=pyo.Binary, doc='Electrolyzer  start from idle')
    model.isIdle = pyo.Var(model.timesteps, domain=pyo.Binary, doc='Electrolyzer is idle')
    model.isStandBy = pyo.Var(model.timesteps, domain=pyo.Binary, doc='Electrolyzer isStandBy')

    # Define the objective function - minimize cost sum within selected timeframe
    model.obj = pyo.Objective(expr=sum(el_PFC[t-1] * model.bidQuantity_MW[t] + coldStartUpCost * model.isColdStarted[t] + slagCost * model.slag[t] for t in model.timesteps), sense=pyo.minimize)

    # Maximale Leistungsgrenze
    def maxPower_rule(model, t):
        if t <= TPrevious:
            return model.elecCons_MW[t] == previousSection["elecCons"][t-1]
        else:
            return model.elecCons_MW[t] <= maxPower * model.isRunning[t] + standbyCons * model.isStandBy[t]
    model.maxPower_rule = pyo.Constraint(model.timesteps, rule=maxPower_rule)

    # Minimale Leistungsgrenze
    def minPower_rule(model, t):
        if t <= TPrevious:
            return model.elecCons_MW[t] == previousSection["elecCons"][t-1]
        else:
            return model.elecCons_MW[t] >= minPower * model.isRunning[t] + standbyCons * model.isStandBy[t]
    model.minPower_rule = pyo.Constraint(model.timesteps, rule=minPower_rule)

    # Nur ein Betriebsmodus
    def statesExclusivity_rule(model, t):
        if t <= TPrevious:
            return pyo.Constraint.Skip
        else:
            return model.isRunning[t] + model.isIdle[t] + model.isStandBy[t] == 1
    model.statesExclusivity = pyo.Constraint(model.timesteps, rule=statesExclusivity_rule)

    # Übergang vom Aus- zum An-Zustand
    def statesExclusivity_2_rule(model, t):
        if t <= TPrevious:
            return pyo.Constraint.Skip
        else:
            if t > 1:
                return model.isColdStarted[t] >= model.isRunning[t] - model.isRunning[t-1] - model.isStandBy[t-1]
            else:
                return model.isColdStarted[t] == 0
    model.statesExclusivity_2 = pyo.Constraint(model.timesteps, rule=statesExclusivity_2_rule)

    # Übergang von einem Aus-Zustand zu einem Standby-Zustand nicht zulässig
    def statesExclusivity_4_rule(model, t):
        if t <= TPrevious:
            return pyo.Constraint.Skip
        else:
            if t > 1:
                return model.isIdle[t-1] + model.isStandBy[t] <= 1
            else:
                return pyo.Constraint.Skip
    model.statesExclusivity_4 = pyo.Constraint(model.timesteps, rule=statesExclusivity_4_rule)

    def statesExclusivity_previous_rule_1(model, t):
        if t <= TPrevious:
            return model.isRunning[t] == previousSection["isRunning"][t-1]
        else:
            return pyo.Constraint.Skip
    model.statesExclusivity_previous_rule_1 = pyo.Constraint(model.timesteps, rule=statesExclusivity_previous_rule_1)

    def statesExclusivity_previous_rule_2(model, t):
        if t <= TPrevious:
            return model.isIdle[t] == previousSection["isIdle"][t-1]
        else:
            return pyo.Constraint.Skip
    model.statesExclusivity_previous_rule_2 = pyo.Constraint(model.timesteps, rule=statesExclusivity_previous_rule_2)

    def statesExclusivity_previous_rule_3(model, t):
        if t <= TPrevious:
            return model.isStandBy[t] == previousSection["isStandBy"][t-1]
        else:
            return pyo.Constraint.Skip
    model.statesExclusivity_previous_rule_3 = pyo.Constraint(model.timesteps, rule=statesExclusivity_previous_rule_3)

    def statesExclusivity_previous_rule_4(model, t):
        if t <= TPrevious:
            return model.isColdStarted[t] == previousSection["isColdStarted"][t-1]
        else:
            return pyo.Constraint.Skip
    model.statesExclusivity_previous_rule_4 = pyo.Constraint(model.timesteps, rule=statesExclusivity_previous_rule_4)

    #minimum downtime constraint
    def minDownTime_rule(model, t):
        if t <= 1:
            return pyo.Constraint.Skip
        else:
            if t > minDownTime:
                return model.isColdStarted[t] * int(minDownTime) <= sum(model.isIdle[j] for j in range(t - int(minDownTime) - 1, t))
            else:
                new_minDownTime = t
                return model.isColdStarted[t] * int(new_minDownTime) <= sum(model.isIdle[j] for j in range(0, int(new_minDownTime)))
    model.minDownTime_rule = pyo.Constraint(model.timesteps, rule=minDownTime_rule)



    # Maximale Anzahl erlaubter Kaltstarts innerhalb eines definierten Zeitraums
    def maxColdStartup_rule(model, t):
        return sum(model.isColdStarted[t] for t in model.timesteps) <= maxAllowedColdStartups
    model.maxColdStartup_rule = pyo.Constraint(model.timesteps, rule=maxColdStartup_rule)
    
    
    # Verbrauch des Elektrolyseurs
    def electrolyzerConsumption_rule(model, t):
        if t <= TPrevious:
            return model.prodH2_kg[t] == previousSection["prodH2"][t-1]
        else:
            return model.prodH2_kg[t] == model.elecCons_MW[t] * effElec / energyContentH2_LHV * (1 - model.isStandBy[t])
    model.electrolyzerConsumption_rule = pyo.Constraint(model.timesteps, rule=electrolyzerConsumption_rule)

    def electrolyzerConsumption_previous_rule(model, t):
        if t <= TPrevious:
            return model.elecCons_MW[t] == previousSection["elecCons"][t-1]
        else:
            return pyo.Constraint.Skip
    model.electrolyzerConsumption_previous_rule = pyo.Constraint(model.timesteps, rule=electrolyzerConsumption_previous_rule)

    # Wasserstoffbilanz
    def hydrogenBalance_rule(model, t):
        if t <= TPrevious:
            return model.prodH2_kg[t] == previousSection["prodH2"][t-1]
        else:
            return model.prodH2_kg[t] == model.elecToPlantUse_kg[t] + model.elecToStorage_kg[t]
    model.hydrogenBalance_rule = pyo.Constraint(model.timesteps, rule=hydrogenBalance_rule)

    # Bedarfsbilanz
    def demandBalance_rule(model, t):
        if t <= TPrevious:
            return pyo.Constraint.Skip
        else:
            return industry_demand[t-1] == model.elecToPlantUse_kg[t] + model.storageToPlantUse_kg[t] + model.slag[t]
    model.demandBalance_rule = pyo.Constraint(model.timesteps, rule=demandBalance_rule)

    # Bilanz previous
    def demandBalance_previous_1_rule(model, t):
        if t <= TPrevious:
            return model.elecToPlantUse_kg[t] == previousSection["elecToPlantUse_kg"][t-1]
        else:
            return pyo.Constraint.Skip
    model.demandBalance_previous_1_rule = pyo.Constraint(model.timesteps, rule=demandBalance_previous_1_rule)

    def demandBalance_previous_2_rule(model, t):
        if t <= TPrevious:
            return model.elecToStorage_kg[t] == previousSection["elecToStorage_kg"][t-1]
        else:
            return pyo.Constraint.Skip
    model.demandBalance_previous_2_rule = pyo.Constraint(model.timesteps, rule=demandBalance_previous_2_rule)

    def demandBalance_previous_3_rule(model, t):
        if t <= TPrevious:
            return model.storageToPlantUse_kg[t] == previousSection["storageToPlantUse_kg"][t-1]
        else:
            return pyo.Constraint.Skip
    model.demandBalance_previous_3_rule = pyo.Constraint(model.timesteps, rule=demandBalance_previous_3_rule)


    # Energieverbrauch des Kompressors
    def compressorCons_rule(model, t):
        if t <= TPrevious:
            return model.comprCons_MW[t] == previousSection["comprCons"][t-1]
        else:
            return model.comprCons_MW[t] == model.elecToStorage_kg[t] * comprCons
    model.compressorCons_rule = pyo.Constraint(model.timesteps, rule=compressorCons_rule)

    # Standby-Verbrauch
    def standByConsumption_rule(model, t):
        if t <= TPrevious:
            return model.elecStandByCons_MW[t] == previousSection["elecStandByCons"][t-1]
        else:
            return model.elecStandByCons_MW[t] == standbyCons * model.isStandBy[t]
    model.standByConsumption_rule = pyo.Constraint(model.timesteps, rule=standByConsumption_rule)

    # Gesamter Verbrauch
    def totalConsumption_rule(model, t):
        if t <= TPrevious:
            return model.bidQuantity_MW[t] == previousSection["optimalBidamount"][t-1]
        else:
            return model.bidQuantity_MW[t] == model.elecCons_MW[t] + model.comprCons_MW[t] # + model.elecColdStartUpCons_MW[i] (Falls erforderlich)
    model.totalConsumption_rule = pyo.Constraint(model.timesteps, rule=totalConsumption_rule)

    # Speicherstand
    def currentSOC_rule(model, t):
        if t <= TPrevious:
            return model.currentSOC_kg[t] == previousSection["currentSOC"][t-1]
        else:
            if t > 1:
                return model.currentSOC_kg[t] == model.currentSOC_kg[t - 1] + model.elecToStorage_kg[t] - model.storageToPlantUse_kg[t]
            else:
                return model.currentSOC_kg[t] == model.elecToStorage_kg[t] - model.storageToPlantUse_kg[t]
    model.currentSOC_rule = pyo.Constraint(model.timesteps, rule=currentSOC_rule)

    # Maximale Speicherfüllung
    def maxSOC_rule(model, t):
        if t <= TPrevious:
            return model.currentSOC_kg[t] == previousSection["currentSOC"][t-1]
        else:
            return model.currentSOC_kg[t] <= maxSOC
    model.maxSOC_rule = pyo.Constraint(model.timesteps, rule=maxSOC_rule)

    # Solve the optimization problem
    opt = SolverFactory("gurobi")  # You can replace this with your preferred solver

    print(log_infeasible_constraints(model))

    result = opt.solve(model) #tee=True
    print('INFO: Electrolyzer Agent: Solver status:', result.solver.status)
    print('INFO: Electrolyzer Agent: Results: ', result.solver.termination_condition)

    dfResults = pd.DataFrame()
    
    # Retrieve the optimal values
    for i in range(1, optHorizon + TPrevious + 1):
        dfResults["optimalBidamount"] = [model.bidQuantity_MW[i].value for i in model.timesteps]
        dfResults["elecCons"] = [model.elecCons_MW[i].value for i in model.timesteps]
        dfResults["elecStandByCons"] = [model.elecStandByCons_MW[i].value for i in model.timesteps]
        dfResults["comprCons"] = [model.comprCons_MW[i].value for i in model.timesteps]
        dfResults["prodH2"] = [model.prodH2_kg[i].value for i in model.timesteps]
        dfResults["elecToPlantUse_kg"] = [model.elecToPlantUse_kg[i].value for i in model.timesteps]
        dfResults["elecToStorage_kg"] = [model.elecToStorage_kg[i].value for i in model.timesteps]
        dfResults["storageToPlantUse_kg"] = [model.storageToPlantUse_kg[i].value for i in model.timesteps]
        dfResults["currentSOC"] = [model.currentSOC_kg[i].value for i in model.timesteps]
        dfResults["isRunning"] = [model.isRunning[i].value for i in model.timesteps]
        dfResults["isStandBy"] = [model.isStandBy[i].value for i in model.timesteps]
        dfResults["isIdle"] = [model.isIdle[i].value for i in model.timesteps]
        dfResults["isColdStarted"] = [model.isColdStarted[i].value for i in model.timesteps]
        dfResults["slag"] = [model.slag[i].value for i in model.timesteps]
        dfResults["H2Demand"] = [industry_demand[i-1] for i in model.timesteps]
        dfResults["elPFC"] = [el_PFC[i-1] for i in model.timesteps]

    x = 2 # HERE: Platzhalter

    return dfResults, x


