import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd


def steelOptBase(optHorizon,
                timestampsPreviousSection, 
                PFC, 
                previousSection,
                productionGoal, 
                maxPower, 
                SOCStart = 0,
                shutDownCosts = 1000000,
                slagCosts = 10000000,
                elConsumption = 1,
                objective="minimize_cost"):
    
    print("--------------Start Optimization Steel Plant-----------------")
        
    # 1. Define the model, sets, and parameters ----------------------------------------------------------------------------

    # 1.1. create the model
    
    model = pyo.ConcreteModel()
    TPrevious = timestampsPreviousSection # number of timesteps of previous section to consider

    # 1.2. set parameter

    # priceforecast
    el_PFC = PFC # assumed production cost = PFC

    # Parameter EAF
    if TPrevious == 0:
        productionGoalTotal = productionGoal
    else:
        productionGoalTotal = productionGoal + sum(previousSection['production'])  # Production goal


    # Parameter storage
    maxCapacity = maxPower * 0.0625 * 30  # max storage capacity
    dischargeRate = 30/32 * maxPower  # discharge rate

    # timesteps
    model.timesteps = pyo.RangeSet(1, optHorizon+TPrevious) 

    # 2. Define the decision variables--------------------------------------------------------------------------------------
    
    # variables storage
    model.charge = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals, initialize=0.0)  # charge
    model.discharge_on = pyo.Var(model.timesteps, domain=pyo.Binary, initialize=0.0) # discharge
    model.SOC = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals, initialize=0.0)  # SOC

    # variables EAF
    model.cons_el = pyo.Var(model.timesteps, within=pyo.NonNegativeReals)  # consumption electricity
    model.production = pyo.Var(model.timesteps, within=pyo.NonNegativeReals)  # production decision
    model.production_slag = pyo.Var(model.timesteps, within=pyo.NonNegativeReals)  # slag if production goal isn´t feasible
    model.next_batch = pyo.Var(model.timesteps, within=pyo.Binary)  # start of the next batch
    model.power_batch = pyo.Var(model.timesteps, within=pyo.NonNegativeReals)  # power of the next batch
    model.shut_down = pyo.Var(model.timesteps, within=pyo.Binary)  # shut down of the plant



    # 3. Define the objective function--------------------------------------------------------------------------------------
    
    # objective function
    if objective == "minimize_cost":
        def obj_rule(model):
            return sum((el_PFC[t-1] * model.cons_el[t] + model.production_slag[t] * slagCosts + model.shut_down[t] * shutDownCosts) for t in model.timesteps)
        model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)
        
    if objective == "maximize_production": # for determining max. production of one section
        def obj_rule(model):
            return sum(model.production[t] for t in model.timesteps)
        model.obj = pyo.Objective(rule=obj_rule, sense=pyo.maximize)

    

    # 4. Define the constraints -----------------------------------------------------------------------------------------

    # 4.1. Constraints EAF 
        
    # 4.1.1. Total production constraint: 
        # Ensure that production goal is reached
    def total_production_rule(model):
        return sum(model.production[t] for t in model.timesteps) + sum(model.production_slag[t] for t in model.timesteps) >= productionGoalTotal
    model.total_production_con = pyo.Constraint(rule=total_production_rule)


    # 4.1.2. Production power constraint: 
        # Define binary for start of a new batch and use this binary to determine power of batch (between 0 and maxPower)
    def production_power_rule_1(model, t):  
        if t <= TPrevious:
            return model.power_batch[t] == previousSection['powerBatch'][t-1]
        else:
            return model.power_batch[t] <= model.next_batch[t] * maxPower
    model.production_power_con_1 = pyo.Constraint(model.timesteps, rule=production_power_rule_1)

    def production_power_rule_2(model, t):
        if t <= TPrevious:
            return model.power_batch[t] == previousSection['powerBatch'][t-1] 
        else:
            return model.power_batch[t] >= model.next_batch[t] 
    model.production_power_con_2 = pyo.Constraint(model.timesteps, rule=production_power_rule_2)

    def production_power_rule_3(model, t):    
        if (optHorizon+TPrevious)-t < 4: # Limiting timesteps to avoid out-of-bounds errors
            return model.power_batch[t] == 0
        else:
            return pyo.Constraint.Skip
    model.production_power_con_3 = pyo.Constraint(model.timesteps, rule=production_power_rule_3)


    # 4.1.3. Batch duration constraint: 
        # If batch started, plant is running 4 timesteps
    def batch_duration_rule(model, t):
        if t <= TPrevious:
            return model.production[t] == previousSection['production'][t-1]
        else:
            return model.production[t] == sum(model.power_batch[tt] for tt in range(t-3, t+1) if tt > 0)
    model.batch_duration_rule= pyo.Constraint(model.timesteps, rule=batch_duration_rule)


    # 4.1.4. Nex batch constraint: 
        # If batch started, next batch can only be started after 4 timesteps
    def next_batch_rule(model, t):
        if t <= TPrevious:
            return model.next_batch[t] == previousSection['nextBatch'][t-1]
        else:
            return model.next_batch[t] <= 1 - sum(model.next_batch[tt] for tt in range(t-3, t) if tt > 0)
    model.next_batch_con = pyo.Constraint(model.timesteps, rule=next_batch_rule)


    # 4.1.5. Downtime constraint:               
        # If storage is empty, plant is off for 20 timesteps
    M_starts = 5 # max possible starts in 20 periods
    def downtime_rule(model, t):
        if t > 1:  # Limiting timesteps to avoid out-of-bounds errors
            return sum(model.next_batch[tt] for tt in range(t, t+21) if tt <= optHorizon+TPrevious) <= (1  - (model.discharge_on[t-1] - model.discharge_on[t])) * M_starts
        return pyo.Constraint.Skip
    model.downtime_con = pyo.Constraint(model.timesteps, rule=downtime_rule)


    # 4.1.6. Shut down constraint:
        # Define binary for shut down
    def shut_down_rule(model, t):
        if t <= TPrevious:
            return model.shut_down[t] == previousSection['shutDown'][t-1]
        else:
            if t > 1:
                return model.discharge_on[t-1] - model.discharge_on[t] >= 2* model.shut_down[t] - 1
            else:
                return model.shut_down[t] == 0
    model.shut_down_con = pyo.Constraint(model.timesteps, rule=shut_down_rule)

    def shut_down_rule2(model, t):
        if t <= TPrevious:
            return model.shut_down[t] == previousSection['shutDown'][t-1]
        else:    
            if t > 1:
                return model.discharge_on[t-1]  <= model.discharge_on[t] + model.shut_down[t]
            else:
                return model.shut_down[t] == 0
    model.shut_down_con2 = pyo.Constraint(model.timesteps, rule=shut_down_rule2)

    #4.1.7. Electricity consumption constraint:
        # Electricity consumption is based on production
    def electricity_consumption_rule(model, t):
        return model.cons_el[t] == model.production[t] * elConsumption
    model.electricity_consumption_con = pyo.Constraint(model.timesteps, rule=electricity_consumption_rule)


    # 4.2. Constraints storage
    
    # 4.2.1 Capacity constraint: 
        # SOC of storage is between zero and maxCapacity
    def capacity_rule1(model, t):
        if t <= TPrevious:
            return model.SOC[t] == previousSection['SOC'][t-1]
        else:
            return model.SOC[t] <= maxCapacity
    model.capacity_con1 = pyo.Constraint(model.timesteps, rule=capacity_rule1)

    def capacity_rule2(model, t):
        if t <= TPrevious:
            return model.SOC[t] == previousSection['SOC'][t-1]
        else:
            return model.SOC[t] >= 0
    model.capacity_con2 = pyo.Constraint(model.timesteps, rule=capacity_rule2)

    # 4.2.2. Energy balance constraint: 
        # Maintain SOC of storage: SOC = previous SOC + charge - discharge
    def energy_balance_rule(model, t):
        if t <= TPrevious:
            return model.SOC[t] == previousSection['SOC'][t-1]
        else:
            if t <= 1: # still need this, if there is no previous section
                return model.SOC[t] == (SOCStart + model.charge[t]) * (model.discharge_on[t]) - model.discharge_on[t] * dischargeRate
            else:
                return model.SOC[t] == (model.SOC[t - 1] + model.charge[t]) * (model.discharge_on[t]) - model.discharge_on[t] * dischargeRate
    model.energy_balance_con = pyo.Constraint(model.timesteps, rule=energy_balance_rule)

    # 4.2.3. Charging constraint:
        ### Unnötiger Constraint --> nur zum besseren Verständnis ###
        # Ensure that charge is equal to production 
    def charging_rule(model,t):
        if t <= TPrevious:
            return model.charge[t] == previousSection['production'][t-1]
        else:
            return model.charge[t] == model.production[t]
    model.charging_con = pyo.Constraint(model.timesteps, rule=charging_rule)

    # 4.2.4. Discharging constraint: 
        ### Define binary for discharging
    def discharging_on_rule1(model,t):
        if t <= TPrevious:
            return model.discharge_on[t] == previousSection['discharge'][t-1]
        else:
            if t > 1:
                return model.discharge_on[t] * dischargeRate <= model.SOC[t - 1] + model.charge[t] 
            else:  
                return model.discharge_on[t] <= SOCStart + model.charge[t]
    model.discharging_on_con1 = pyo.Constraint(model.timesteps, rule=discharging_on_rule1)

    def discharging_on_rule2(model,t):
        if t <= TPrevious:
            return model.discharge_on[t] == previousSection['discharge'][t-1]
        else:
            if t > 1:
                return model.discharge_on[t] * (maxCapacity+maxPower) + dischargeRate - 0.001 >= model.SOC[t - 1] + model.charge[t]  # evtl. noch + dischargeRate, weil sonst SOC zu niedrig
            else:
                return model.discharge_on[t] * maxCapacity >= SOCStart + model.charge[t]
    model.discharging_on_con2 = pyo.Constraint(model.timesteps, rule=discharging_on_rule2)

    def discharging_on_rule3(model,t):
        if t <= TPrevious:
            return model.discharge_on[t] == previousSection['discharge'][t-1]
        else:
            if t >= 5:
                return model.discharge_on[t] >= sum(model.next_batch[tt] for tt in range(t-3, t+1) if tt > 0)
            else:
                return pyo.Constraint.Skip
    model.discharging_on_con3 = pyo.Constraint(model.timesteps, rule=discharging_on_rule3)



    # 5. Solve the model
    solver = pyo.SolverFactory('gurobi')

    results = solver.solve(model)

    dfResults = pd.DataFrame(columns=["nextBatch", "powerBatch", "production", "shutDown", "SOC", "discharge"])
            
    for i in range (1, optHorizon+TPrevious+1):
        dfResults["nextBatch"] = [model.next_batch[t]() for t in model.timesteps]
        dfResults["powerBatch"] = [model.power_batch[t]() for t in model.timesteps]
        dfResults["production"] = [model.production[t]() for t in model.timesteps]
        dfResults["shutDown"] = [model.shut_down[t]() for t in model.timesteps]
        dfResults["SOC"] = [model.SOC[t]() for t in model.timesteps]
        dfResults["el_consumption"] = [model.cons_el[t]() for t in model.timesteps]
        dfResults["discharge"] = [model.discharge_on[t]() for t in model.timesteps]
        dfResults["slag"] = [model.production_slag[t]() for t in model.timesteps]

    productionCostSection = [model.obj()]
    slagSection = sum([model.production_slag[t]() for t in model.timesteps])

    dfResults.to_csv("output/2016example/SteelPlant/resultsSteelPlantOpt.csv")
        
    return dfResults, productionCostSection, slagSection