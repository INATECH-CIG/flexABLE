import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd
import numpy as np
import logging


def prodGoalOpt(timestampsTotal,
                  timestampsSection,
                  PFC, 
                  productionGoal,
                  maxProductionSection):
    
    print("Optimization for production goal started")
    
    # 1. Define the model, sets, and parameters ----------------------------------------------------------------------------
    
    # 1.1. create the model
    
    model = pyo.ConcreteModel()
    timestampsSection = int(timestampsSection) # number of timesteps per section (24)
    T_optimization = int(timestampsTotal / timestampsSection) # number of timesteps per optimization (24 * 4)
    
    # 1.2. set parameter

    # priceforecast
    el_PFC = PFC
    slagCosts = 1000000000

    # summarize cost of each section
    cost_section = np.array([el_PFC[i * timestampsSection: (i + 1) * timestampsSection] for i in range(T_optimization)])
    cost_section = np.sum(cost_section,axis=1)

    # timesteps
    model.timesteps = pyo.RangeSet(1, T_optimization)




    # 2. Define the decision variables ----------------------------------------------------------------------------
    model.production_section = pyo.Var(model.timesteps, within=pyo.NonNegativeIntegers)  # production in section
    model.slag = pyo.Var(model.timesteps, within=pyo.NonNegativeIntegers)  # slag in section



    # 3. Define the objective function  ----------------------------------------------------------------------------
    def obj_rule(model):
        return sum(model.production_section[t] * cost_section[t-1] + model.slag[t] * slagCosts for t in model.timesteps)
    model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)



    # 4. Define the constraints  ----------------------------------------------------------------------------
    
    # 4.1. Total production constraint: 
        # Ensure that production goal is reached
    def total_production_rule(model):
        return sum(model.production_section[t] + model.slag[t] for t in model.timesteps) >= productionGoal
    model.total_production_con = pyo.Constraint(rule=total_production_rule)

    # 4.2. Max production section:
        # Ensure that production in one section is smaller than maxProductionSection
    def production_section_rule(model, t):
        return model.production_section[t] <= maxProductionSection
    model.production_section_con = pyo.Constraint(model.timesteps, rule=production_section_rule)

    # 5. Solve the model
    solver = pyo.SolverFactory('gurobi')
    results = solver.solve(model)

    
    return model
