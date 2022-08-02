# %%
from SteelPlant import SteelPlant

plant_1 = SteelPlant(name='Test1',max_capacity=3000, min_production=2000)

# %%

plant_1.limits

plant_1.process_opt


# %%

plant_2 = SteelPlant(
                 name = 'KKW ISAR 2',
                 technology = 'Steel_Plant',
                 max_capacity = 1500,
                 min_production = 0,
                 profit_margin = 0.,
                 optimization_horizon = 24,
                 node = 'Bus_DE',
                 world = None)

plant_2.optimization_horizon

# %%
SteelPlant.process_opt(plant_2)
# %%
