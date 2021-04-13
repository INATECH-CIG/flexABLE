import pyomo.environ as pyo


class MarketClearing():
    def __init__(self, solver):
        self.opt = pyo.SolverFactory(solver)

        self.model = pyo.AbstractModel()
        
        self.model.indexSupplyMR = pyo.Set()
        self.model.indexSupplyFlex = pyo.Set()
        self.model.indexDemand = pyo.Set()
        
        self.model.IED = pyo.Param()
        
        self.model.mrPower = pyo.Param(self.model.indexSupplyMR)
        self.model.mrPrice = pyo.Param(self.model.indexSupplyMR)
        self.model.mrTotal = pyo.Param(self.model.indexSupplyMR)
        
        self.model.flexPower = pyo.Param(self.model.indexSupplyFlex)
        self.model.flexPrice = pyo.Param(self.model.indexSupplyFlex)
        self.model.flexTotal = pyo.Param(self.model.indexSupplyFlex)
        
        self.model.demandPower = pyo.Param(self.model.indexDemand)
        self.model.demandPrice = pyo.Param(self.model.indexDemand)
        self.model.demandTotal = pyo.Param(self.model.indexDemand)
        
        self.model.flexOrder = pyo.Var(self.model.indexSupplyFlex, domain = pyo.NonNegativeReals, bounds=(0,1))
        self.model.mrOrder = pyo.Var(self.model.indexSupplyMR, domain = pyo.Binary)
        self.model.demandOrder = pyo.Var(self.model.indexDemand, domain = pyo.NonNegativeReals, bounds=(0,1))
        
        # relaxation variables
        self.model.relaxPower = pyo.Var(domain = pyo.NonNegativeReals)

        def energyBalanceRule(model):
            return pyo.quicksum((pyo.summation(model.flexPower, model.flexOrder),
                                 pyo.summation(model.mrPower, model.mrOrder),
                                 model.relaxPower)) == model.IED + pyo.summation(model.demandPower, model.demandOrder)
        
        def objective(model):
            return pyo.quicksum((pyo.summation(model.mrTotal, model.mrOrder),
                                 pyo.summation(model.flexTotal, model.flexOrder),
                                 pyo.summation(model.demandTotal, model.demandOrder)*(-1),
                                 model.relaxPower*1000))
        
        self.model.energyBalanceRule = pyo.Constraint(rule=energyBalanceRule)
        
        self.model.objective = pyo.Objective(rule=objective, sense=pyo.minimize)
        

        
    def clear(self, data):

        self.instance = self.model.create_instance(data)
        self.opt.solve(self.instance)
        
        return self.instance

    
    