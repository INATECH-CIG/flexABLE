import pyomo.environ as pyo
import numpy as np
import random 


# Define the model
model = pyo.ConcreteModel()

# 1. Define the model, sets, and parameters.
T = 96  # number of timesteps
production_goal = 92
maxPower = 4
minPower = 0
model.timesteps = pyo.RangeSet(1, T)

# Production cost function
# production_cost = [1, 2, 0, 3, 4, 1, 0, 2, 4, 1, 3, 2, 0, 4, 2, 1, 0, 4, 3, 2, 1, 0, 4, 3, 2, 1, 0, 4, 3, 2, 1,0,3,3,3]
production_cost = (np.sin(np.linspace(0, 8*np.pi, T)) + 1) * 50
production_cost = [_ for _ in range(T+3)]
production_cost = [random.randint(0,4) for _ in range(T+3)]
production_cost_sum = []
for i in range(len(production_cost)):
    total = 0
    for j in range(i, min(i + 4, len(production_cost))):  # Beachte das Randproblem am Ende
        total += production_cost[j]
    production_cost_sum.append(total)

# 2. Define the decision variables.
model.start = pyo.Var(model.timesteps, within=pyo.Binary)  # start of the plant
model.run_power = pyo.Var(model.timesteps, within=pyo.Integers)  # power of the plant

# 3. Define the objective function.
def obj_rule(model):
    return sum((production_cost[t-1] + production_cost[t] + production_cost[t+1] + production_cost[t+2]) * model.run_power[t] for t in model.timesteps)
model.obj = pyo.Objective(rule=obj_rule, sense=pyo.minimize)

# 4. Define the constraints.
# Total production constraint
def total_production_rule(model):
    return sum(model.run_power[t] for t in model.timesteps) == production_goal/4
model.total_production_con = pyo.Constraint(rule=total_production_rule)

# Production is only possible if plant is on
def production_on_rule_1(model, t):
    return model.run_power[t] <= model.start[t] * maxPower
model.production_on_con_1 = pyo.Constraint(model.timesteps, rule=production_on_rule_1)

def production_on_rule_2(model, t):
    return model.run_power[t] >= model.start[t] 
model.production_on_con_2 = pyo.Constraint(model.timesteps, rule=production_on_rule_2)


# Start if no start occurred in preceding 3 periods
def start_rule(model, t):
    return model.start[t] <= 1 - sum(model.start[tt] for tt in range(t-3, t) if tt > 0)
model.start_con = pyo.Constraint(model.timesteps, rule=start_rule)



# Shut-down window constraint
M_starts = 5 # max possible starts in 20 periods
def shutdown_window_rule(model, t):
    if t > 5:  # Limiting timesteps to avoid out-of-bounds errors
        return sum(model.start[tt] for tt in range(t+3, t+21) if tt <= T) <= (1 - (model.start[t-4] - model.start[t])) * M_starts
    # else:
    #     return model.start[t] == 0
    return pyo.Constraint.Skip
model.shutdown_window_con = pyo.Constraint(model.timesteps, rule=shutdown_window_rule)


# 5. Solve the model using Gurobi.
solver = pyo.SolverFactory('gurobi')
results = solver.solve(model)










import matplotlib.pyplot as plt
# 6. Plot the results.
x_values = [model.run_power[t]() for t in model.timesteps]
i = 0
while i < len(x_values):
    if x_values[i] > 0:
        value_to_propagate = x_values[i]
        for j in range(i, min(i + 4, len(x_values))):
            x_values[j] = value_to_propagate
        i += 4
    else:
        i += 1
y_values = [model.run_power[t]() for t in model.timesteps]
batch_over_values = [model.start[t]() for t in model.timesteps]

# Create a plot with 3 subplots
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, sharex=True, figsize=(15, 10))

# Plot the production decision
ax1.step(range(1, T+1), x_values, where='post', label="Production (x)", color='blue')
ax1.set_ylabel("Value")
ax1.legend()
ax1.grid(True)

# Plot the plant status
ax2.step(range(1, T+1), y_values, where='post', label="Plant running", color='red', linestyle='--')
ax2.step(range(1, T+1), batch_over_values, where='post', label="Plant started", color='blue', linestyle=':')
ax2.set_ylabel("Value")
ax2.legend()
ax2.grid(True)

# Setze die x-Achse für alle Achsen gleich
ax3.step(range(1, T+4), production_cost, where='post', label="Production Cost", color='green', linestyle=':')
ax3.set_ylabel("Value")
ax3.set_xlabel("Timesteps")
ax3.legend()
ax3.grid(True)
ax3.set_xlim(1, T+4)  # Setze die x-Achsen-Grenzen für alle Plots

# Füge Hilfslinien bei jedem Zeitschritt hinzu
ax3.set_xticks(range(1, T+5))  # Hier wird 5 anstelle von 4 verwendet, um auch den letzten Zeitschritt zu berücksichtigen

# Plot the summarizied production cost
ax3.step(range(1, T+4), production_cost_sum, where='post', label="Production Cost Sum", color='red', linestyle=':')
ax3.set_ylabel("Value")
ax3.set_xlabel("Timesteps")
ax3.legend()
ax3.grid(True)

for t in range(1, T+4):
    value = production_cost_sum[t-1]
    ax3.text(t, value, str(value), ha='center', va='bottom')

# Zeige die Grafik
plt.show()