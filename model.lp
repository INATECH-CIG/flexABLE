\ LP format - for model browsing. Use MPS format to capture full model detail.
Maximize
  - 30 Supply_Bids('WEISWEILER_G_mrEOM',_0)
   - 30 Supply_Bids('WEISWEILER_G_flexEOM',_0)
   - 10 Supply_Bids('KKW_ISAR_2_mrEOM',_0)
   - 10 Supply_Bids('KKW_ISAR_2_flexEOM',_0)
   - 20 Supply_Bids('BREMEN_HAFEN_6_mrEOM',_0)
   - 20 Supply_Bids('BREMEN_HAFEN_6_flexEOM',_0)
   + 500 Supply_Bids('Wind_Onshore_[MW]_mrEOM',_0)
   + 500 Supply_Bids('Solar_[MW]_mrEOM',_0)
   + 3000 Demand_Bids('TestStahl_SteelPlant_demandEOM',_0)
   + 3000 Demand_Bids('IEDt0',_0)
Subject To
 Energy_Balance: Supply_Bids('WEISWEILER_G_mrEOM',_0)
   + Supply_Bids('WEISWEILER_G_flexEOM',_0)
   + Supply_Bids('KKW_ISAR_2_mrEOM',_0)
   + Supply_Bids('KKW_ISAR_2_flexEOM',_0)
   + Supply_Bids('BREMEN_HAFEN_6_mrEOM',_0)
   + Supply_Bids('BREMEN_HAFEN_6_flexEOM',_0)
   + Supply_Bids('Wind_Onshore_[MW]_mrEOM',_0)
   + Supply_Bids('Solar_[MW]_mrEOM',_0)
   + Supply_Bids('TestStahl_SteelPlant_supplyEOM',_0)
   - Demand_Bids('TestStahl_SteelPlant_demandEOM',_0)
   - Demand_Bids('IEDt0',_0) = 0
Bounds
 Supply_Bids('WEISWEILER_G_mrEOM',_0) <= 100
 Supply_Bids('WEISWEILER_G_flexEOM',_0) <= 5900
 Supply_Bids('KKW_ISAR_2_mrEOM',_0) <= 100
 Supply_Bids('KKW_ISAR_2_flexEOM',_0) <= 1385
 Supply_Bids('BREMEN_HAFEN_6_mrEOM',_0) <= 100
 Supply_Bids('BREMEN_HAFEN_6_flexEOM',_0) <= 230
 Supply_Bids('Wind_Onshore_[MW]_mrEOM',_0) <= 1000
 Supply_Bids('Solar_[MW]_mrEOM',_0) <= 800
 Supply_Bids('TestStahl_SteelPlant_supplyEOM',_0) = 0
 Demand_Bids('TestStahl_SteelPlant_demandEOM',_0) = 0
 Demand_Bids('IEDt0',_0) <= 3308
End
