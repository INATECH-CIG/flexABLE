import pyomo.environ as pyo
import numpy as np
import random 


# Define the model
model = pyo.ConcreteModel()

# 1. Define the model, sets, and parameters.
T = 56  # number of timesteps
production_goal = 32
maxPower = 2
minPower = 0
model.timesteps = pyo.RangeSet(1, T)

# Production cost function
production_cost = (np.sin(np.linspace(0, 8*np.pi, T)) + 1) * 50
production_cost = [_ for _ in range(T)]
production_cost = [random.randint(1,100) for _ in range(T)]

# 2. Define the decision variables.
model.production = pyo.Var(model.timesteps, within=pyo.Integers)  # production decision
model.running = pyo.Var(model.timesteps, within=pyo.Binary)  # plant status
model.start = pyo.Var(model.timesteps, within=pyo.Binary)  # start of the plant

# 3. Define the objective function.
def obj_rule(model):
    return sum(production_cost[t-1] * model.production[t] for t in model.timesteps)
model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)

# 4. Define the constraints.
# Total production constraint
def total_production_rule(model):
    return sum(model.production[t] for t in model.timesteps) == production_goal
model.total_production_con = pyo.Constraint(rule=total_production_rule)


# Production is only possible if plant is on
def production_on_rule_1(model, t):
    return model.production[t] <= model.running[t] * maxPower
model.production_on_con_1 = pyo.Constraint(model.timesteps, rule=production_on_rule_1)

def production_on_rule_2(model, t):
    return model.production[t] >= model.running[t] 
model.production_on_con_2 = pyo.Constraint(model.timesteps, rule=production_on_rule_2)


# Running if started in current or preceding 3 periods
def running_rule(model, t):
    return model.running[t] <= sum(model.start[tt] for tt in range(t-3, t+1) if tt > 0)
model.running_con = pyo.Constraint(model.timesteps, rule=running_rule)

# Start if no start occurred in preceding 3 periods
def start_rule(model, t):
    return model.start[t] <= 1 - sum(model.start[tt] for tt in range(t-3, t) if tt > 0)
model.start_con = pyo.Constraint(model.timesteps, rule=start_rule)

# Shut-down window constraint
M_starts = 5 # max possible starts in 20 periods
def shutdown_window_rule(model, t):
    if t > 3:  # Limiting timesteps to avoid out-of-bounds errors
        return sum(model.start[tt] for tt in range(t+3, t+21) if tt <= T) <= (1 - (model.running[t-1] - model.running[t])) * M_starts
    return pyo.Constraint.Skip
model.shutdown_window_con = pyo.Constraint(model.timesteps, rule=shutdown_window_rule)

# Ensure that when the plant starts, it runs for the current and next three periods.
def block_start_rule(model, t):
    if t <= T-3:
        return model.running[t] + model.running[t+1] + model.running[t+2] + model.running[t+3]>= 4 * model.start[t]
    return pyo.Constraint.Skip
model.block_start_con = pyo.Constraint(model.timesteps, rule=block_start_rule)


# # Ensure that when the plant starts, it runs for the current and next three periods whith equal power.
# def block_production_rule_1(model, t):
#     if t <= T-3:
#         return model.production[t+1] * model.running[t] == model.production[t] * model.start[t]
#     return pyo.Constraint.Skip
# model.block_production_rule_1 = pyo.Constraint(model.timesteps, rule=block_production_rule_1)

# def block_production_rule_2(model,t):
#     if t <= T-3:
#         return model.production[t+2] * model.running[t]== model.production[t] * model.start[t]
#     return pyo.Constraint.Skip
# model.block_production_rule_2 = pyo.Constraint(model.timesteps, rule=block_production_rule_2)

# def block_production_rule_3(model,t):
#     if t <= T-3:
#         return model.production[t+3] * model.running[t]== model.production[t] * model.start[t]
#     return pyo.Constraint.Skip
# model.block_production_rule_3 = pyo.Constraint(model.timesteps, rule=block_production_rule_3)




# 5. Solve the model using Gurobi.
solver = pyo.SolverFactory('gurobi')
results = solver.solve(model)

import matplotlib.pyplot as plt
# 6. Plot the results.
x_values = [model.production[t]() for t in model.timesteps]
y_values = [model.running[t]() for t in model.timesteps]
batch_over_values = [model.start[t]() for t in model.timesteps]

# Create a plot with 3 subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 6))

# Plot the production decision
ax1.step(range(1, T+1), x_values, where='post', label="Production (x)", color='blue')
ax1.set_xticks(range(1, T+1))
ax1.set_ylabel("Value")
ax1.legend()
ax1.grid(True)

# Plot the plant status
ax2.step(range(1, T+1), y_values, where='mid', label="Plant running", color='red', linestyle='--')
ax2.step(range(1, T+1), batch_over_values, where='mid', label="Plant started", color='blue', linestyle=':')
ax2.set_ylabel("Value")
ax2.legend()
ax2.grid(True)

# Plot the production cost
ax3.step(range(1, T+1), production_cost, where='mid', label="Production Cost", color='green', linestyle=':')
ax3.set_xlabel("Timesteps")
ax3.set_ylabel("Value")
ax3.legend()
ax3.grid(True)

# Add a title
plt.suptitle("Steel Plant Production Schedule")
plt.show()