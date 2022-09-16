# %% import all packages
import numpy as np 
import pandas as pd
from datetime import datetime
from tqdm.notebook import tqdm
from torch.utils.tensorboard import SummaryWriter
from flexABLE import World

# %% run training on defined scenario
scenario ={'scenario':'dsm_test/case_01', 'id':'dsm_01', 'year':2019, 'days':10, 'scale':10}
if 'opt' in scenario['id']:
    opt_storages = True
    rl_mode = False
elif 'base' in scenario['id']:
    opt_storages = False
    rl_mode = False
else: 
    opt_storages = False
    rl_mode = True

dt=1

training_episodes = 1000
learning_starts = 30

snapLength = int(24/dt*scenario['days'])
timeStamps = pd.date_range(
    '{}-01-01T00:00:00'.format(scenario['year']), '{}-01-01T00:00:00'.format(scenario['year']+1), freq='15T')

startingPoint = '2019-03-01 00:00'
startingPoint = timeStamps.get_loc(startingPoint)

world = World(snapshots=snapLength,
              scenario=scenario['scenario'],
              simulation_id=scenario['id'],
              starting_date=timeStamps[startingPoint],
              dt=dt,
              enable_CRM=False,
              enable_DHM=False,
              check_availability=False,
              write_to_db=False,
              rl_mode=False,
              training=False,
              save_policies=True,
              learning_starts=learning_starts,
              load_params=False)
              #load_params={'id': scenario['id'], 'dir': 'best_policy', 'load_critics': False})

# %% Load scenario
world.load_scenario(startingPoint=startingPoint,
                    importStorages=True,
                    import_dsm_units = True,
                    opt_storages=opt_storages,
                    importCBT=False,
                    scale=scenario['scale'])

# %% Start training
index = pd.date_range(world.starting_date, periods=len(world.snapshots), freq=str(60*world.dt)+'T')

if world.training and world.rl_mode:
    training_start = datetime.now()
    world.logger.info("################")
    world.logger.info('Training started at: {}'.format(training_start))

    for i_episode in tqdm(range(training_episodes), desc='Training'):
        start = datetime.now()
        world.run_simulation()
                
        if ((i_episode + 1) % 5 == 0) and world.episodes_done > learning_starts+10:
            world.training = False
            world.run_evaluation()
            world.training = True

            tempDF = pd.DataFrame(world.mcp, index=index, columns=['Simulation']).astype('float64')
            if world.write_to_db:
                world.results_writer.writeDataFrame(tempDF, 'Prices', tags={'simulationID': world.simulation_id, "user": "EOM"})
                world.results_writer.write_storages()

        if ((i_episode + 1) % 5 == 0) and world.episodes_done > learning_starts+10:
            for pp in world.rl_powerplants:
                pp.save_params(file_name=str(world.eval_episodes_done)+'_ep')

    training_end = datetime.now()
    world.logger.info("################")
    world.logger.info('Training time: {}'.format(training_end - training_start))

    if world.write_to_db:
        world.training=False
        for unit in world.rl_powerplants+world.rl_storages:
            unit.load_params(load_params={'id': scenario['id'], 'dir': 'best_policy'})
        world.run_evaluation()
        world.results_writer.save_results_to_DB()
        world.logger.info("################")

else:
    start = datetime.now()
    world.run_evaluation()
    if world.rl_mode:
        world.logger.info('Total reward: {}'.format(world.eval_rewards[-1]))
        world.logger.info('Average profit: {}'.format(world.eval_profits[-1]))
        world.logger.info('Average regret: {}'.format(world.eval_regrets[-1]))
    
    end = datetime.now()
    world.logger.info('Simulation time: {}'.format(end - start))

    if world.write_to_db:
        world.results_writer.save_results_to_DB()
    world.logger.info("################")


# %%
# historic_prices = pd.read_csv('input/{}/Historic_Prices.csv'.format(scenario['scenario']),
#                               index_col = 0)

# historic_prices.index = pd.to_datetime(historic_prices.index, unit='ms')
# historic_prices = historic_prices[1:]

# tempDF = pd.DataFrame(historic_prices['Historic_Data'].values,
#                       index = pd.date_range('{}-01-01T00:00:00'.format(scenario['year']), '{}-12-31T23:00:00'.format(scenario['year']), freq = '1H'),
#                       columns = ['Historic Price']).astype('float64')

# #world.results_writer.writeDataFrame(tempDF, 'Historic MCP', tags = {'simulation_id':world.simulation_id, "user": "EOM"})

# # %%
# from sklearn.metrics import mean_squared_error, mean_absolute_error

# modelled_prices = pd.DataFrame(index = index, data = world.mcp, columns = ['Modelled MCP'])
# #modelled_prices = modelled_prices.resample('1H').mean()

# rmse = mean_squared_error(historic_prices['Historic_Data'],
#                           modelled_prices['Modelled MCP'])**0.5


# print('RMSE:', round(rmse, 2))

# mae = mean_absolute_error(historic_prices['Historic_Data'],
#                           modelled_prices['Modelled MCP'])

# print('MAE:', round(mae, 2))

# %%
