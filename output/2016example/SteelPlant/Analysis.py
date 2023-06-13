import os
import pandas as pd

# Ordnerpfad definieren
ordner_pfad = 'C:/Users/Hendrik Wulfert/Projekte/IND-E/Flexable/flexABLE- master_5_grafana'

# Liste mit allen Dateien erstellen
output_pfad = ordner_pfad + "/output/2016example/SteelPlant"
dateien = os.listdir(output_pfad)

# Anzahl der Dateien zählen
anzahl_dateien = len(dateien)

# Bestimmung der Segmentzahl aus der flexABLE Berechnung

segmente = int(anzahl_dateien-3)


#%% Zusammenfügen der Daten

# Produktionsplan
prod_opt = pd.DataFrame()
for i in range(0,segmente):
    df = pd.read_csv(f'{output_pfad}/prod_opt_{i}.csv', sep = ';')
    
    if i == 0:
        prod_opt = df
    else:
        df = pd.concat([pd.DataFrame({f'prod_opt_{i}': [None] * (len(prod_opt) - len(df))}), df])
        df = df.set_index(prod_opt.index)
        prod_opt = pd.concat([prod_opt,df],axis=1)


PFC_pfad = ordner_pfad + "/output/2016example/SteelPlant/PFC.csv"
PFC = pd.read_csv(PFC_pfad, sep=';')
PFC.columns = ["PFC"]
EOM_pfad = ordner_pfad + "/output/2016example/EOM_Prices.csv"
EOM_Price = pd.read_csv(EOM_pfad)
Production_SP_pfad = ordner_pfad + "/output/2016example/PP_capacities/TestStahl_Capacity.csv"
Production = pd.read_csv(Production_SP_pfad)

summary = pd.concat([PFC,prod_opt, EOM_Price['Price'],Production['Power']], axis=1)


summary.to_csv(f'{output_pfad}/summarized/summary.csv', index=False)
