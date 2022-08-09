# %%
from flexABLE import World
import pandas as pd
# %%
scenario = 'dsm_test'
year = 2019
days = 10

importStorages = False
importCRM = False
importDHM = False
importCBT = False
checkAvailability = False
meritOrder = True

writeResultsToDB = False


startingPoint = 0
snapLength = 96*days    
timeStamps = pd.date_range('{}-01-01T00:00:00'.format(year), '{}-01-01T00:00:00'.format(year+1), freq = '15T')

env = World(snapLength,
                simulationID = 'example',
                startingDate = timeStamps[startingPoint],
                writeResultsToDB = writeResultsToDB)


env.loadScenario(scenario = scenario,
                        checkAvailability=checkAvailability,
                        importStorages=importStorages,
                        importCRM=importCRM,
                        importCBT=importCBT,
                        importDHM=importDHM,
                        meritOrder=meritOrder)

# %%
env.runSimulation()