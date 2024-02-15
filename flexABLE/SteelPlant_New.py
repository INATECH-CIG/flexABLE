def cost_opt_base(self,
                      start = None,
                      OptimizationHorizon = None,
                      importCRM = None
                      ):

        print(start, "Optimization")

        if OptimizationHorizon is None: 
            OptimizationHorizon = len(self.world.snapshots) - 1
        
        if start is None:
            start = 0

        

        restProduction = self.requierdProduction - sum(list(self.dictCapacity.values())[0:start])

        solver = pyo.SolverFactory('glpk')
        
        PFC_EOM = self.dicPFC
        
        # create model
        model = pyo.ConcreteModel()
        
        # set horizon
        model.t = pyo.RangeSet(start, OptimizationHorizon)
        
        #set variables
        model.product = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        
        #set objective
        def cost_obj_rule(model):
            return pyo.quicksum((model.product[t]*PFC_EOM[t]) for t in model.t)
        
        model.obj = pyo.Objective(rule = cost_obj_rule, sense = pyo.minimize)
        
        #set constraints
        def product_max_rule(model,t):
            return model.product[t] <= self.maxPower 
        def product_min_rule(model,t):
            return model.product[t] >= self.minPower
        def product_total_rule(model,t):
            return pyo.quicksum(model.product[t] for t in model.t) >= restProduction
        

        def product_max_rule(model,t):
            if start % self.crmTime != 0 and importCRM:
                time = start % self.crmTime
                if t in range(start, start + time):
                    return model.product[t] <= self.maxPower - self.confQtyCRM_neg_amount[start] 
                else:
                    return model.product[t] <= self.maxPower 
            else:
                return model.product[t] <= self.maxPower 
        
        model.production_total_rule = pyo.Constraint(model.t, rule=product_total_rule)
        model.production_max_rule = pyo.Constraint(model.t, rule=product_max_rule)
        model.production_min_rule = pyo.Constraint(model.t, rule=product_min_rule)
        
        #solve model
        solver.solve(model)
        
        prod_base = []
        
        for i in range (start, OptimizationHorizon+1):
            prod_base.append(model.product[i].value)
            
        return prod_base

cost_opt_base()