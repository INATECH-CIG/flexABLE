import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd
from pyomo.util.infeasible import log_infeasible_constraints





def cementOptBase(
        optHorizon,
        timestampsPreviousSection,
        PFC,
        previousSection,
        productionGoal,
        minPowerRawMill,
        maxPowerRawMill,
        minPowerKiln,
        maxPowerKiln,
        minPowerCementMill,
        maxPowerCementMill,
        maxCapRawMealSilo,
        maxCapClinkerDome,
        elConsRawMill, # electricity consumption of raw mill per ton
        elConsKiln, # electricity consumption of kiln per ton
        elConsCementMill, # electricity consumption of cement mill per ton
        slagCosts,
        objective = 'minimize_cost',
):


    # 1. Define the model, sets, and parameters ----------------------------------------------------------------------------

    print('Start optimization cement plant')

    print('Optimization horizon: ', optHorizon)


    previousSection.to_csv("output/2016example/CementPlant/previousSection.csv")

    # 1.1. create the model

    model = pyo.ConcreteModel()
    TPrevious = timestampsPreviousSection # number of timesteps of previous section to consider


    # 1.2. set parameter

    # priceforecast
    el_PFC = PFC


    # production
    if TPrevious == 0:
        productionGoalTotal = productionGoal
    else:
        productionGoalTotal = productionGoal + sum(previousSection['output_cement_mill'])  # Production goal

    # timesteps
    model.timesteps = pyo.RangeSet(1, optHorizon+TPrevious) 

    # process parameter


    rawMillClinkerFactor = 1.61 # t rawmill/t clinker #HERE not sure if i use it right maybe "kehrwert"
    clinkerCementFactor = 0.86 # t clinker/t cement #HERE not sure if i use it right maybe "kehrwert"


    # 2. Define the decision variables--------------------------------------------------------------------------------------

    model.input_raw_mill = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # input of raw mill
    model.el_cons_raw_mill = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # electricity consumption of raw mill
    model.output_raw_mill = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # output of raw mill
    model.raw_mill_shut_down = pyo.Var(model.timesteps, domain=pyo.Binary) # raw mill shut down
    model.raw_mill_shut_down_change = pyo.Var(model.timesteps, domain=pyo.Binary) # raw mill shut down change
    model.raw_mill_on = pyo.Var(model.timesteps, domain=pyo.Binary) # raw mill on/off
    model.raw_mill_start = pyo.Var(model.timesteps, within=pyo.Binary)
    model.raw_mill_stop = pyo.Var(model.timesteps, within=pyo.Binary)
    model.raw_mill_blocked_time_con = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # raw mill blocked time


    model.input_kiln = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # input of kiln
    model.el_cons_kiln = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # electricity consumption of kiln
    model.output_kiln = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # output of kiln
    model.kiln_on = pyo.Var(model.timesteps, domain=pyo.Binary) # kiln on/off

    model.input_cement_mill = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # input of cement mill
    model.el_cons_cement_mill = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # electricity consumption of cement mill
    model.output_cement_mill = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals) # output of cement mill
    model.cement_mill_shut_down = pyo.Var(model.timesteps, domain=pyo.Binary) # cement mill shut down
    model.cement_mill_shut_down_change = pyo.Var(model.timesteps, domain=pyo.Binary) # cement mill shut down change
    model.cement_mill_on = pyo.Var(model.timesteps, domain=pyo.Binary) # cement mill on/off
    model.cement_mill_start = pyo.Var(model.timesteps, within=pyo.Binary)
    model.cement_mill_stop = pyo.Var(model.timesteps, within=pyo.Binary)

    model.raw_meal_silo = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals, initialize=0.0) # raw meal silo

    model.clinker_dome = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals, initialize=0.0) # clinker dome

    model.production_slag = pyo.Var(model.timesteps, domain=pyo.NonNegativeReals, initialize=0.0) # production of slag

    # 3. Define the objective function--------------------------------------------------------------------------------------

    # objective function

    if objective == 'minimize_cost':
        def obj_rule(model):
            return sum(el_PFC[t-1] * (model.el_cons_raw_mill[t] + model.el_cons_kiln[t] + model.el_cons_cement_mill[t]) + model.production_slag[t] * slagCosts for t in model.timesteps)
        model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)

    if objective == 'maximize_production':
        def obj_rule(model):
            return sum(model.output_cement_mill[t] for t in model.timesteps)
        model.obj = pyo.Objective(rule=obj_rule, sense=pyo.maximize)

    # 4. Define the constraints -----------------------------------------------------------------------------------------

    def total_production_rule(model):
        return sum(model.output_cement_mill[t] for t in model.timesteps) + sum(model.production_slag[t] for t in model.timesteps) >= productionGoalTotal
    model.total_production_con = pyo.Constraint(rule=total_production_rule)


    # # 4.3. production constraints raw mill

    def previous_raw_mill_on_rule(model, t): # necessary to set previous input kiln, otherwise its empty (not necessary for optimization but maybe for analyses purpose)
        if t <= TPrevious:# or t == max(model.timesteps):
            #if t <= TPrevious:
            return model.raw_mill_on[t] == previousSection['raw_mill_on'][t-1]
            # else:
            #     return model.raw_mill_on[t] == 0
        else:
            return pyo.Constraint.Skip
    model.previous_raw_mill_on_con = pyo.Constraint(model.timesteps, rule=previous_raw_mill_on_rule)

  
    # Regel zur Definition von raw_mill_start, wenn der Zustand von "aus" zu "an" wechselt
    def raw_mill_start_rule_1(model, t):
        if t <= TPrevious:
            return model.raw_mill_start[t] == previousSection['raw_mill_start'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_start[t] == 0
            else:
                return model.raw_mill_start[t] >= model.raw_mill_on[t] - model.raw_mill_on[t-1]
    model.raw_mill_start_con_1 = pyo.Constraint(model.timesteps, rule=raw_mill_start_rule_1)

    def raw_mill_start_rule_2(model, t):
        if t <= TPrevious:
            return model.raw_mill_start[t] == previousSection['raw_mill_start'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_start[t] == 0
            else:
                return model.raw_mill_start[t] <= (model.raw_mill_on[t] - model.raw_mill_on[t-1] +1)/2
    model.raw_mill_start_con_2 = pyo.Constraint(model.timesteps, rule=raw_mill_start_rule_2)

    # Regel zur Definition von raw_mill_stop, wenn der Zustand von "an" zu "aus" wechselt
    def raw_mill_stop_rule_1(model, t):
        if t <= TPrevious:
            return model.raw_mill_stop[t] == previousSection['raw_mill_stop'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_stop[t] == 0
            else:
                return model.raw_mill_stop[t] >= (model.raw_mill_on[t] - model.raw_mill_on[t-1]) * (-1)
    model.raw_mill_stop_con_1 = pyo.Constraint(model.timesteps, rule=raw_mill_stop_rule_1)

    def raw_mill_stop_rule_2(model, t):
        if t <= TPrevious:
            return model.raw_mill_stop[t] == previousSection['raw_mill_stop'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_stop[t] == 0
            else:
                return model.raw_mill_stop[t] <= ((model.raw_mill_on[t] - model.raw_mill_on[t-1]) * (-1) + 1)/2
    model.raw_mill_stop_con_2 = pyo.Constraint(model.timesteps, rule=raw_mill_stop_rule_2)


    # Regel zur Definition Anlage im "Warmbetrieb" (shutdown = 1) und "Kaltbetrieb" (shutdown = 0)
    def raw_mill_shutdown_rule(model, t):
        if t <= TPrevious:
            return model.raw_mill_shut_down[t] == previousSection['raw_mill_shut_down'][t-1]
        else:
            if t >= min(model.timesteps) + 4:
                return sum((1 - model.raw_mill_on[t - k]) for k in range(5)) - 4 <= 100*(1 - model.raw_mill_shut_down[t])
            else:
                return model.raw_mill_on[t] == model.raw_mill_shut_down[t]
                #return pyo.Constraint.Skip
    model.raw_mill_shutdown_con = pyo.Constraint(model.timesteps, rule=raw_mill_shutdown_rule)

    def shutdown_rule_2(model, t):
        if t <= TPrevious:
            return model.raw_mill_shut_down[t] == previousSection['raw_mill_shut_down'][t-1]
        else:
            if t >= min(model.timesteps) + 4:
                return 5 - sum((1 - model.raw_mill_on[t - k]) for k in range(5)) <= 100 * model.raw_mill_shut_down[t]
            else:
                return model.raw_mill_on[t] == model.raw_mill_shut_down[t]
                #return pyo.Constraint.Skip
                return pyo.Constraint.Skip
    model.raw_mill_shutdown_con_2 = pyo.Constraint(model.timesteps, rule=shutdown_rule_2)


    # Regel zur Definition von raw_mill_shut_down_change, wenn der Zustand von "aus" zu "an" wechselt
    def raw_mill_shutdown_change_rule_1(model, t):
        if t <= TPrevious:
            return model.raw_mill_shut_down_change[t] == previousSection['raw_mill_shut_down_change'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_shut_down_change[t] == 1
            else:
                return model.raw_mill_shut_down_change[t] + 1 >= model.raw_mill_shut_down[t-1] + model.raw_mill_shut_down[t]
    model.raw_mill_shutdown_change_con_1 = pyo.Constraint(model.timesteps, rule=raw_mill_shutdown_change_rule_1)

    def raw_mill_shutdown_change_rule_2(model, t):
        if t <= TPrevious:
            return model.raw_mill_shut_down_change[t] == previousSection['raw_mill_shut_down_change'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_shut_down_change[t] == 1
            else:
                return 1 - model.raw_mill_shut_down_change[t] <= model.raw_mill_shut_down[t-1]
    model.raw_mill_shutdown_change_con_2 = pyo.Constraint(model.timesteps, rule=raw_mill_shutdown_change_rule_2)

    def raw_mill_shutdown_change_rule_3(model, t):
        if t <= TPrevious:
            return model.raw_mill_shut_down_change[t] == previousSection['raw_mill_shut_down_change'][t-1]
        else:
            if t == model.timesteps.first():
                return model.raw_mill_shut_down_change[t] == 1
            else:
                return 1 - model.raw_mill_shut_down_change[t] >= model.raw_mill_shut_down[t-1] - model.raw_mill_shut_down[t]
    model.raw_mill_shutdown_change_con_3 = pyo.Constraint(model.timesteps, rule=raw_mill_shutdown_change_rule_3)


    # Regel zur Sicherstellung der Mindestbetriebsdauer nach einer Abschaltung von 1 bis 16 Zeitschritten
    def raw_mill_min_operation_after_downtime_rule(model, t):
        if t <= max(model.timesteps) - 15:
            return sum(model.raw_mill_on[t + k] for k in range(16)) >= 16 * model.raw_mill_start[t]
        else:
            raw_mill_on_time = max(model.timesteps) - t
            return sum(model.raw_mill_on[t + k] for k in range(raw_mill_on_time+1)) >= (raw_mill_on_time+1) * model.raw_mill_start[t]
    model.raw_mill_min_operation_after_downtime_con = pyo.Constraint(model.timesteps, rule=raw_mill_min_operation_after_downtime_rule)


    # Regel zur Sicherstellung der Mindestbetriebsdauer nach einer Komplettabschaltung von 1 bis 12 Zeitschritten
    def raw_mill_min_offtime_after_downtime_rule(model, t):
        if t <= max(model.timesteps) - 11:
            return sum(1 - model.raw_mill_on[t + k] for k in range(12)) >= 12 * (1 - model.raw_mill_shut_down_change[t])
        else:
            raw_mill_off_time = max(model.timesteps) - t
            return sum(1 - model.raw_mill_on[t + k] for k in range(raw_mill_off_time+1)) >= (raw_mill_off_time+1) * (1 - model.raw_mill_shut_down_change[t])
    model.raw_mill_min_offtime_after_downtime_con = pyo.Constraint(model.timesteps, rule=raw_mill_min_offtime_after_downtime_rule)

    # Regel zur Definition der Produktionsmenge
    def production_raw_mill_rule_1(model, t):
        if t <= TPrevious:
            return model.output_raw_mill[t] == previousSection['output_raw_mill'][t-1]
        else:
            return model.output_raw_mill[t] <= maxPowerRawMill * model.raw_mill_on[t]
    model.production_raw_mill_con_1 = pyo.Constraint(model.timesteps, rule=production_raw_mill_rule_1)

    def production_raw_mill_rule_2(model, t):
        if t <= TPrevious:
            return model.output_raw_mill[t] == previousSection['output_raw_mill'][t-1]
        else:
            return model.output_raw_mill[t] >= minPowerRawMill * model.raw_mill_on[t]
    model.production_raw_mill_con_2 = pyo.Constraint(model.timesteps, rule=production_raw_mill_rule_2)

    # Regel zur Definition der elektrischen Verbrauchsmenge
    def el_cons_raw_mill_rule_1(model, t):
        return model.el_cons_raw_mill[t] == model.output_raw_mill[t] * elConsRawMill
    model.el_cons_raw_mill_con_1 = pyo.Constraint(model.timesteps, rule=el_cons_raw_mill_rule_1)

    # 4.4. constraints raw meal silo

    def capacity_raw_meal_silo_rule_1(model, t):
        if t <= TPrevious:
            return model.raw_meal_silo[t] == previousSection['raw_meal_silo'][t-1]
        else:
            return model.raw_meal_silo[t] <= maxCapRawMealSilo
    model.capacity_raw_meal_silo_con_1 = pyo.Constraint(model.timesteps, rule=capacity_raw_meal_silo_rule_1)

    def capacity_raw_meal_silo_rule_2(model, t):
        if t <= TPrevious:
            return model.raw_meal_silo[t] == previousSection['raw_meal_silo'][t-1]
        else:
            if t == max(model.timesteps):
                return model.raw_meal_silo[t] >= 0 + (model.kiln_on[t] * maxPowerKiln/rawMillClinkerFactor) 
            else:
                return model.raw_meal_silo[t] >= 0
    model.capacity_raw_meal_silo_con_2 = pyo.Constraint(model.timesteps, rule=capacity_raw_meal_silo_rule_2)

    def balance_raw_meal_silo_rule(model, t):
        if t <= TPrevious:
            return model.raw_meal_silo[t] == previousSection['raw_meal_silo'][t-1]
        else:
            if t <= 1:
                return model.raw_meal_silo[t] == 0 + model.output_raw_mill[t] - model.input_kiln[t]
            else:
                return model.raw_meal_silo[t] == model.raw_meal_silo[t-1] + model.output_raw_mill[t] - model.input_kiln[t]
    model.balance_raw_meal_silo_con = pyo.Constraint(model.timesteps, rule=balance_raw_meal_silo_rule)

    def previous_input_kiln_rule(model, t): # necessary to set previous input kiln, otherwise its empty (not necessary for optimization but maybe for analyses purpose) 
        if t <= TPrevious:
            return model.input_kiln[t] == previousSection['input_kiln'][t-1]
        else:
            return pyo.Constraint.Skip
    model.previous_input_kiln_con = pyo.Constraint(model.timesteps, rule=previous_input_kiln_rule)


    # 4.5. production constraints kiln

    def production_kiln_rule_1(model, t):
        if t <= TPrevious:
            return model.output_kiln[t] == previousSection['output_kiln'][t-1]
        else:
            return model.output_kiln[t] == model.input_kiln[t] * rawMillClinkerFactor 
    model.production_kiln_1 = pyo.Constraint(model.timesteps, rule=production_kiln_rule_1)

    def production_kiln_rule_2(model, t):
        if t <= TPrevious:
            return model.output_kiln[t] == previousSection['output_kiln'][t-1]
        else:
            return model.output_kiln[t] <= maxPowerKiln  * model.kiln_on[t]
    model.production_kiln_2 = pyo.Constraint(model.timesteps, rule=production_kiln_rule_2)

    def production_kiln_rule_3(model, t):
        if t <= TPrevious:
            return model.output_kiln[t] == previousSection['output_kiln'][t-1]
        else:
            return model.output_kiln[t] >= model.kiln_on[t] * minPowerKiln
    model.production_kiln_3 = pyo.Constraint(model.timesteps, rule=production_kiln_rule_3)

    def production_kiln_rule_4(model, t): #Dauerbetrieb
        if t <= TPrevious:
            return model.kiln_on[t] == previousSection['kiln_on'][t-1]
        else:
            return model.kiln_on[t] == 1
    model.production_kiln_4 = pyo.Constraint(model.timesteps, rule=production_kiln_rule_4)

    def el_cons_kiln_rule_1(model, t):
        if t <= TPrevious:
            return model.el_cons_kiln[t] == previousSection['el_cons_kiln'][t-1]
        else:
            return model.el_cons_kiln[t] == model.output_kiln[t] * elConsKiln
    model.el_cons_kiln_1 = pyo.Constraint(model.timesteps, rule=el_cons_kiln_rule_1)


    # 4.6. constraints clinker dome

    def capacity_clinker_dome_rule_1(model, t):
        if t <= TPrevious:
            return model.clinker_dome[t] == previousSection['clinker_dome'][t-1]
        else:
            return model.clinker_dome[t] <= maxCapClinkerDome
    model.capacity_clinker_dome_con_1 = pyo.Constraint(model.timesteps, rule=capacity_clinker_dome_rule_1)

    def capacity_clinker_dome_rule_2(model, t):
        if t <= TPrevious:
            return model.clinker_dome[t] == previousSection['clinker_dome'][t-1]
        else:
            if t == max(model.timesteps):
                return model.clinker_dome[t] >= 0 + model.cement_mill_on[t] *  maxPowerCementMill/clinkerCementFactor # to ensure valid SOC for next section if cement_mill is allread running
            else:
                return model.clinker_dome[t] >= 0
    model.capacity_clinker_dome_con_2 = pyo.Constraint(model.timesteps, rule=capacity_clinker_dome_rule_2)

    def balance_clinker_dome_rule(model, t):
        if t <= TPrevious:
            return model.clinker_dome[t] == previousSection['clinker_dome'][t-1]
        else:
            if t <= 1:
                return model.clinker_dome[t] == 0 + model.output_kiln[t] - model.input_cement_mill[t]
            else:
                return model.clinker_dome[t] == model.clinker_dome[t-1] + model.output_kiln[t] - model.input_cement_mill[t]
    model.balance_clinker_dome_con = pyo.Constraint(model.timesteps, rule=balance_clinker_dome_rule)


    # 4.7. production constraints cement mill

    def previous_cement_mill_on_rule(model, t): # necessary to set previous input kiln, otherwise its empty (not necessary for optimization but maybe for analyses purpose)
        if t <= TPrevious:# or t == max(model.timesteps):
            #if t <= TPrevious:
            return model.cement_mill_on[t] == previousSection['cement_mill_on'][t-1]
            # else:
            #     return model.cement_mill_on[t] == 0
        else:
            return pyo.Constraint.Skip
    model.previous_cement_mill_on_con = pyo.Constraint(model.timesteps, rule=previous_cement_mill_on_rule)

    
    def previous_input_cement_mill_rule(model, t): # necessary to set previous input kiln, otherwise its empty (not necessary for optimization but maybe for analyses purpose) 
        if t <= TPrevious:
            return model.input_cement_mill[t] == previousSection['input_cement_mill'][t-1]
        else:
            return pyo.Constraint.Skip
    model.previous_input_cement_mill_con = pyo.Constraint(model.timesteps, rule=previous_input_cement_mill_rule)



    # Rule to define cement_mill_start when transitioning from "off" to "on" state
    def cement_mill_start_rule_1(model, t):
        if t <= TPrevious:
            return model.cement_mill_start[t] == previousSection['cement_mill_start'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_start[t] == 0
            else:
                return model.cement_mill_start[t] >= model.cement_mill_on[t] - model.cement_mill_on[t-1]
    model.cement_mill_start_con_1 = pyo.Constraint(model.timesteps, rule=cement_mill_start_rule_1)

    def cement_mill_start_rule_2(model, t):
        if t <= TPrevious:
            return model.cement_mill_start[t] == previousSection['cement_mill_start'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_start[t] == 0
            else:
                return model.cement_mill_start[t] <= (model.cement_mill_on[t] - model.cement_mill_on[t-1] + 1) / 2
    model.cement_mill_start_con_2 = pyo.Constraint(model.timesteps, rule=cement_mill_start_rule_2)

    # Rule to define cement_mill_stop when transitioning from "on" to "off" state
    def cement_mill_stop_rule_1(model, t):
        if t <= TPrevious:
            return model.cement_mill_stop[t] == previousSection['cement_mill_stop'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_stop[t] == 0
            else:
                return model.cement_mill_stop[t] >= (model.cement_mill_on[t] - model.cement_mill_on[t-1]) * (-1)
    model.cement_mill_stop_con_1 = pyo.Constraint(model.timesteps, rule=cement_mill_stop_rule_1)

    def cement_mill_stop_rule_2(model, t):
        if t <= TPrevious:
            return model.cement_mill_stop[t] == previousSection['cement_mill_stop'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_stop[t] == 0
            else:
                return model.cement_mill_stop[t] <= ((model.cement_mill_on[t] - model.cement_mill_on[t-1]) * (-1) + 1) / 2
    model.cement_mill_stop_con_2 = pyo.Constraint(model.timesteps, rule=cement_mill_stop_rule_2)

    # Rule to define mill in "warm operation" (shutdown = 1) and "cold operation" (shutdown = 0)
    def cement_mill_shutdown_rule(model, t):
        if t <= TPrevious:
            return model.cement_mill_shut_down[t] == previousSection['cement_mill_shut_down'][t-1]
        else:
            if t >= min(model.timesteps) + 4:
                return sum((1 - model.cement_mill_on[t - k]) for k in range(5)) - 4 <= 100 * (1 - model.cement_mill_shut_down[t])
            else:
                return model.raw_mill_on[t] == model.raw_mill_shut_down[t]
                #return pyo.Constraint.Skip
    model.cement_mill_shutdown_con = pyo.Constraint(model.timesteps, rule=cement_mill_shutdown_rule)

    def cement_mill_shutdown_rule_2(model, t):
        if t <= TPrevious:
            return model.cement_mill_shut_down[t] == previousSection['cement_mill_shut_down'][t-1]
        else:
            if t >= min(model.timesteps) + 4:
                return 5 - sum((1 - model.cement_mill_on[t - k]) for k in range(5)) <= 100 * model.cement_mill_shut_down[t]
            else:
                return model.raw_mill_on[t] == model.raw_mill_shut_down[t]
                #return pyo.Constraint.Skip
    model.cement_mill_shutdown_con_2 = pyo.Constraint(model.timesteps, rule=cement_mill_shutdown_rule_2)

    # Rule to define cement_mill_shut_down_change when transitioning from "off" to "on" state
    def cement_mill_shutdown_change_rule_1(model, t):
        if t <= TPrevious:
            return model.cement_mill_shut_down_change[t] == previousSection['cement_mill_shut_down_change'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_shut_down_change[t] == 1
            else:
                return model.cement_mill_shut_down_change[t] + 1 >= model.cement_mill_shut_down[t-1] + model.cement_mill_shut_down[t]
    model.cement_mill_shutdown_change_con_1 = pyo.Constraint(model.timesteps, rule=cement_mill_shutdown_change_rule_1)

    def cement_mill_shutdown_change_rule_2(model, t):
        if t <= TPrevious:
            return model.cement_mill_shut_down_change[t] == previousSection['cement_mill_shut_down_change'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_shut_down_change[t] == 1
            else:
                return 1 - model.cement_mill_shut_down_change[t] <= model.cement_mill_shut_down[t-1]
    model.cement_mill_shutdown_change_con_2 = pyo.Constraint(model.timesteps, rule=cement_mill_shutdown_change_rule_2)

    def cement_mill_shutdown_change_rule_3(model, t):
        if t <= TPrevious:
            return model.cement_mill_shut_down_change[t] == previousSection['cement_mill_shut_down_change'][t-1]
        else:
            if t == model.timesteps.first():
                return model.cement_mill_shut_down_change[t] == 1
            else:
                return 1 - model.cement_mill_shut_down_change[t] >= model.cement_mill_shut_down[t-1] - model.cement_mill_shut_down[t]
    model.cement_mill_shutdown_change_con_3 = pyo.Constraint(model.timesteps, rule=cement_mill_shutdown_change_rule_3)

    # Rule to ensure minimum operating duration after a shutdown from 1 to 16 time steps
    def cement_mill_min_operation_after_downtime_rule(model, t):
        if t <= max(model.timesteps) - 15:
            return sum(model.cement_mill_on[t + k] for k in range(16)) >= 16 * model.cement_mill_start[t]
        else:
            cement_mill_on_time = max(model.timesteps) - t
            return sum(model.cement_mill_on[t + k] for k in range(cement_mill_on_time+1)) >= (cement_mill_on_time+1) * model.cement_mill_start[t]
    model.cement_mill_min_operation_after_downtime_con = pyo.Constraint(model.timesteps, rule=cement_mill_min_operation_after_downtime_rule)

    # Rule to ensure minimum downtime after a complete shutdown from 1 to 12 time steps
    def cement_mill_min_offtime_after_downtime_rule(model, t):
        if t <= max(model.timesteps) - 11:
            return sum(1 - model.cement_mill_on[t + k] for k in range(12)) >= 12 * (1 - model.cement_mill_shut_down_change[t])
        else:
            cement_mill_off_time = max(model.timesteps) - t
            return sum(1 - model.cement_mill_on[t + k] for k in range(cement_mill_off_time+1)) >= (cement_mill_off_time+1) * (1 - model.cement_mill_shut_down_change[t])
    model.cement_mill_min_offtime_after_downtime_con = pyo.Constraint(model.timesteps, rule=cement_mill_min_offtime_after_downtime_rule)

    def production_cement_mill_rule_1(model, t):
        if t <= TPrevious:
            return model.output_cement_mill[t] == previousSection['output_cement_mill'][t-1]
        else:
            return model.output_cement_mill[t] == model.input_cement_mill[t] * clinkerCementFactor 
    model.production_cement_mill_1 = pyo.Constraint(model.timesteps, rule=production_cement_mill_rule_1)

    def production_cement_mill_rule_2(model, t):
        if t <= TPrevious:
            return model.output_cement_mill[t] == previousSection['output_cement_mill'][t-1]
        else:
            return model.output_cement_mill[t] <= maxPowerCementMill * model.cement_mill_on[t]
    model.production_cement_cement_mill_1 = pyo.Constraint(model.timesteps, rule=production_cement_mill_rule_2)

    def production_cement_mill_rule_3(model, t):
        if t <= TPrevious:
            return model.output_cement_mill[t] == previousSection['output_cement_mill'][t-1]
        else:
            return model.output_cement_mill[t] >= minPowerCementMill * model.cement_mill_on[t]
    model.production_cement_cement_mill_3 = pyo.Constraint(model.timesteps, rule=production_cement_mill_rule_3)

    def el_cons_cement_mill_rule_1(model, t):
        if t <= TPrevious:
            return model.el_cons_cement_mill[t] == previousSection['el_cons_cement_mill'][t-1]
        else:
            return model.el_cons_cement_mill[t] == model.output_cement_mill[t] * elConsCementMill
    model.el_cons_cement_mill_1 = pyo.Constraint(model.timesteps, rule=el_cons_cement_mill_rule_1)

    # 5. Solve the model -----------------------------------------------------------------------------------------

    solver = pyo.SolverFactory('gurobi')
   # log_infeasible_constraints(model)

    results = solver.solve(model, tee=False)


    # Plotten

    results_df = pd.DataFrame()

    results_df["output_raw_mill"] = [model.output_raw_mill[t]() for t in model.timesteps]
    results_df["el_cons_raw_mill"] = [model.el_cons_raw_mill[t]() for t in model.timesteps]
    results_df["raw_mill_on"] = [model.raw_mill_on[t]() for t in model.timesteps]
    results_df["raw_mill_start"] = [model.raw_mill_start[t]() for t in model.timesteps]
    results_df["raw_mill_stop"] = [model.raw_mill_stop[t]() for t in model.timesteps]
    results_df["raw_mill_shut_down"] = [model.raw_mill_shut_down[t]() for t in model.timesteps]
    results_df["raw_mill_shut_down_change"] = [model.raw_mill_shut_down_change[t]() for t in model.timesteps]
    results_df["input_kiln"] = [model.input_kiln[t]() for t in model.timesteps]
    results_df["output_kiln"] = [model.output_kiln[t]() for t in model.timesteps]
    results_df["el_cons_kiln"] = [model.el_cons_kiln[t]() for t in model.timesteps]
    results_df["kiln_on"] = [model.kiln_on[t]() for t in model.timesteps]
    results_df["el_cons_cement_mill"] = [model.el_cons_cement_mill[t]() for t in model.timesteps]
    results_df["cement_mill_on"] = [model.cement_mill_on[t]() for t in model.timesteps]
    results_df["cement_mill_start"] = [model.cement_mill_start[t]() for t in model.timesteps]
    results_df["cement_mill_stop"] = [model.cement_mill_stop[t]() for t in model.timesteps]
    results_df["cement_mill_shut_down"] = [model.cement_mill_shut_down[t]() for t in model.timesteps]
    results_df["cement_mill_shut_down_change"] = [model.cement_mill_shut_down_change[t]() for t in model.timesteps]
    results_df["input_cement_mill"] = [model.input_cement_mill[t]() for t in model.timesteps]
    results_df["output_cement_mill"] = [model.output_cement_mill[t]() for t in model.timesteps]
    results_df["raw_meal_silo"] = [model.raw_meal_silo[t]() for t in model.timesteps]
    results_df["clinker_dome"] = [model.clinker_dome[t]() for t in model.timesteps]
    results_df["el_cons_total"] = results_df["el_cons_raw_mill"] + results_df["el_cons_kiln"] + results_df["el_cons_cement_mill"]
    results_df["slag"] = [model.production_slag[t]() for t in model.timesteps]

    results_df.to_csv("output/2016example/CementPlant/resultsCementPlantOpt.csv")

    # # um Randproblem zu korrigieren
    # # Anzahl der letzten Einträge, die überprüft werden sollen
    # num_entries = 16

    # # Überprüfen, ob in den letzten num_entries Einträgen der Spalte 'raw_mill_shut_down_change' der Wert 0 vorhanden ist
    # if 0 in results_df['raw_mill_shut_down_change'].tail(num_entries).values:
    #     # Speicher um fehlende Produktion anpassen
    #     results_df.loc[results_df.index[-1:], 'raw_meal_silo'] -= results_df.loc[results_df.index[-num_entries:], 'output_raw_mill']
    #     # Die letzten num_entries Einträge der angegebenen Spalten auf 0 setzen
    #     results_df.loc[results_df.index[-1:], 'output_raw_mill'] = 0
    #     results_df.loc[results_df.index[-1:], 'el_cons_raw_mill'] = 0
    #     results_df.loc[results_df.index[-1:], 'raw_mill_on'] = 0
    #     results_df.loc[results_df.index[-1:], 'raw_mill_start'] = 0
    #     results_df.loc[results_df.index[-1:], 'raw_mill_stop'] = 0
    #     results_df.loc[results_df.index[-1:], 'raw_mill_shut_down'] = 0
    #     # Den letzten Wert von 'raw_mill_shut_down_change' auf 1 setzen
    #     results_df.at[results_df.index[-1], 'raw_mill_shut_down_change'] = 1
        

    
    x = "temp" # Placeholder for the return value


    return results_df, x

