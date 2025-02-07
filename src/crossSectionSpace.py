"""
Optimizes for the fundamental period by seeking cross-sections of all structural elements
"""
from analysis.openseesrun import OpenSeesRun
from utils.ipbsd_utils import initiate_msg, success_msg
from utils.performance_obj_verifications import check_period

import numpy as np
import constraint
import pandas as pd


class CrossSectionSpace:
    def __init__(self, data, period_limits, fstiff, iteration=False, reduce_combos=True):
        """
        Initialize
        :param data: object                        IPBSD input data
        :param period_limits: dict                  Period limits identified via IPBSD
        :param fstiff: float                        Stiffness reduction factor (initial assumption)
        :param iteration: bool                      Whether iterations are being carried out via IPBSD
        :param reduce_combos: bool                  Reduce number of combinations to be created (adds more constraints)
        """
        self.data = data
        self.period_limits = period_limits
        self.fstiff = fstiff
        self.iteration = iteration
        self.reduce_combos = reduce_combos

        # number of storeys
        self.nst = data.nst
        # number of bays in X and Y directions
        self.nbays_x = len(data.spans_x)
        self.nbays_y = len(data.spans_y)

        # Self-weight of reinforced concrete, kN/m3
        self.SELF_WEIGHT = 25.

        # Solution files
        self.solutions = None
        self.solutions_x = None
        self.solutions_y = None
        self.solutions_gr = None
        self.elements = None

    def read_solutions(self, export_directory=None):
        """

        :param export_directory: str                        Directory where cache of solutions needs to be exported to
        :return: None
        """
        # Export solution as cache in .csv (initialize)
        if export_directory:
            if not self.iteration and not export_directory.exists():
                initiate_msg("Getting initial section combinations satisfying period bounds. Might take a while...")
                elements_cache_path = export_directory.parents[0] / "elements_space.csv"
                if not elements_cache_path.exists():
                    self.elements = self.define_constraint_function()
                    # Export solutions as cache in .csv
                    self.elements.to_csv(elements_cache_path)
                else:
                    self.elements = pd.read_csv(elements_cache_path, index_col=[0])

                # Get all solutions within the period limits
                self.solutions, self.solutions_x, self.solutions_y, self.solutions_gr = self.get_all_solutions()

                # Export solutions as cache in .csv
                self.solutions.to_csv(export_directory)
                self.solutions_x.to_csv(export_directory.parents[0] / "solution_cache_space_x.csv")
                self.solutions_y.to_csv(export_directory.parents[0] / "solution_cache_space_y.csv")
                self.solutions_gr.to_csv(export_directory.parents[0] / "solution_cache_space_gr.csv")

            # If solutions file exists, read and derive the solutions
            if export_directory.exists():
                # Iterative phase
                initiate_msg("Reading files containing initial section combinations satisfying period bounds...")
                self.solutions = pd.read_csv(export_directory, index_col=[0])
                self.solutions_x = pd.read_csv(export_directory.parents[0] / "solution_cache_space_x.csv",
                                               index_col=[0])
                self.solutions_y = pd.read_csv(export_directory.parents[0] / "solution_cache_space_y.csv",
                                               index_col=[0])
                self.solutions_gr = pd.read_csv(export_directory.parents[0] / "solution_cache_space_gr.csv",
                                                index_col=[0])

    def get_all_solutions(self):
        """
        Gets all possible solutions respecting the period bounds in both directions
        :return: dict                       All possible solutions within a period range
        """
        hinge = {"x_seismic": None, "y_seismic": None, "gravity": None}
        # Create the DataFrames for the space system
        columns = []
        columns_gr = []
        for st in range(1, self.data.nst + 1):
            columns.append(f"he{st}")
            columns.append(f"hi{st}")
            columns.append(f"b{st}")
            columns.append(f"h{st}")
            columns_gr.append(f"hi{st}")
            columns_gr.append(f"bx{st}")
            columns_gr.append(f"hx{st}")
            columns_gr.append(f"by{st}")
            columns_gr.append(f"hy{st}")

        # Initialize
        solutions_x = pd.DataFrame(columns=columns)
        solutions_y = pd.DataFrame(columns=columns)
        solutions_gr = pd.DataFrame(columns=columns_gr)
        # Principal modal periods
        solutions_x["T"] = ""
        solutions_y["T"] = ""
        # Weight of structural components
        solutions_x["Weight"] = ""
        solutions_y["Weight"] = ""
        # Effective modal masses
        solutions_x["Mstar"] = ""
        solutions_y["Mstar"] = ""
        # Modal participation factors
        solutions_x["Part Factor"] = ""
        solutions_y["Part Factor"] = ""

        # Space systems will be used for 3D modelling only
        solutions = pd.DataFrame(columns=self.elements.columns)
        # Principal modal periods
        solutions["T1"] = ""
        solutions["T2"] = ""
        # Weight of structural components
        solutions["Weight"] = ""
        # Effective modal masses
        solutions["Mstar1"] = ""
        solutions["Mstar2"] = ""
        # Modal participation factors
        solutions["Part Factor1"] = ""
        solutions["Part Factor2"] = ""

        for i in self.elements.index:
            # Get element cross-sections of solution i
            ele = self.elements.iloc[i]
            # Generate section properties
            cs = self.get_section(ele)
            # Run modal analysis via OpenSeesPy
            op = OpenSeesRun(self.data, cs, self.fstiff, system="space", hinge=hinge)
            op.create_model()
            op.define_masses()
            num_modes = self.nst if self.nst <= 9 else 9
            periods, modalShape, gamma, mstar = op.run_modal_analysis(num_modes)
            op.wipe()

            # Verify that both periods are within the period limits
            if check_period(periods[0], self.period_limits["1"][0], self.period_limits["1"][1], tol=0.01, pflag=False) \
                    and check_period(periods[0], self.period_limits["2"][0], self.period_limits["2"][1], pflag=False):

                weight = self.get_weight(ele)
                solutions_x = solutions_x.append(cs["x_seismic"], ignore_index=True)
                solutions_y = solutions_y.append(cs["y_seismic"], ignore_index=True)
                solutions_gr = solutions_gr.append(cs["gravity"], ignore_index=True)

                solutions_x.at[solutions_x.index[-1], 'T'] = periods[0]
                solutions_y.at[solutions_y.index[-1], 'T'] = periods[1]
                solutions_x.at[solutions_x.index[-1], 'Weight'] = weight
                solutions_y.at[solutions_y.index[-1], 'Weight'] = weight
                solutions_x.at[solutions_x.index[-1], 'Mstar'] = mstar[0]
                solutions_y.at[solutions_y.index[-1], 'Mstar'] = mstar[1]
                solutions_x.at[solutions_x.index[-1], 'Part Factor'] = gamma[0]
                solutions_y.at[solutions_y.index[-1], 'Part Factor'] = gamma[1]

                # All solutions
                solutions = solutions.append(ele, ignore_index=True)

                solutions.at[solutions.index[-1], 'T1'] = periods[0]
                solutions.at[solutions.index[-1], 'T2'] = periods[1]
                solutions.at[solutions.index[-1], 'Weight'] = weight
                solutions.at[solutions.index[-1], 'Mstar1'] = mstar[0]
                solutions.at[solutions.index[-1], 'Mstar2'] = mstar[1]
                solutions.at[solutions.index[-1], 'Part Factor1'] = gamma[0]
                solutions.at[solutions.index[-1], 'Part Factor2'] = gamma[1]

        return solutions, solutions_x, solutions_y, solutions_gr

    def get_section(self, ele):
        """
        Reformat cross-section information for readability by OpenSeesRun3D object
        :param ele: Series                      Element cross-sections
        :return: dict                           Dictionary subdivided into x, y and internal frames
        """

        # Create the Series
        cs_x = {}
        cs_y = {}
        cs_int = {}
        for st in range(1, self.nst + 1):
            # X direction
            cs_x[f"he{st}"] = ele[f"h11{st}"]
            cs_x[f"hi{st}"] = ele[f"h21{st}"]
            cs_x[f"b{st}"] = ele[f"bx11{st}"]
            cs_x[f"h{st}"] = ele[f"hx11{st}"]
            # Y direction
            cs_y[f"he{st}"] = ele[f"h11{st}"]
            cs_y[f"hi{st}"] = ele[f"h12{st}"]
            cs_y[f"b{st}"] = ele[f"by11{st}"]
            cs_y[f"h{st}"] = ele[f"hy11{st}"]
            # Internal
            cs_int[f"hi{st}"] = ele[f"h22{st}"]
            cs_int[f"bx{st}"] = ele[f"bx12{st}"]
            cs_int[f"hx{st}"] = ele[f"hx12{st}"]
            cs_int[f"by{st}"] = ele[f"by21{st}"]
            cs_int[f"hy{st}"] = ele[f"hy21{st}"]
        # If modal parameters are available
        try:
            # Weight will be related to the entire structural inventory of the building
            cs_x["Weight"] = ele["Weight"]
            cs_x["T"] = ele["T1"]
            cs_x["Mstar"] = ele["Mstar1"]
            cs_x["Part Factor"] = ele["Part Factor1"]

            cs_y["Weight"] = ele["Weight"]
            cs_y["T"] = ele["T2"]
            cs_y["Mstar"] = ele["Mstar2"]
            cs_y["Part Factor"] = ele["Part Factor2"]
        except:
            # Central/internal (gravity) key does not need to have information on modal properties
            pass

        # Into a Series
        cs_x = pd.Series(cs_x, name=ele.name, dtype="float")
        cs_y = pd.Series(cs_y, name=ele.name, dtype="float")
        cs_int = pd.Series(cs_int, name=ele.name, dtype="float")

        # Assign to dictionary (gravity i.e. internal elements)
        cs = {"x_seismic": cs_x, "y_seismic": cs_y, "gravity": cs_int}

        return cs

    def fix_dependencies(self, key, main, perp, gravity):
        # Storey of hive element
        storey = int(key[-1])

        # Elements storey-wise
        for st in range(1, self.nst, 2):
            if storey % 2 == 0:
                hive = f"{key[:-1]}{st+1}"
                bee = f"{key[:-1]}{st}"
            else:
                hive = f"{key[:-1]}{st}"
                bee = f"{key[:-1]}{st+1}"
            main[bee] = main[hive]
            # Force allowable variations of c-s dimensions between elements of adjacent groups
            if st <= self.nst - 2:
                hive = f"{key[:-1]}{st+2}"
                bee = f"{key[:-1]}{st}"
                if main[hive] > main[bee]:
                    main[bee] = main[hive]
                    main[f"{key[:-1]}{st+1}"] = main[bee]

        if key[:-1] == "he":
            # Constraints for columns in perpendicular direction
            for st in range(1, self.nst + 1):
                perp[f"he{st}"] = main[f"he{st}"]
                # Constrain beam widths not be larger than the column height
                hive = f"b{st}"
                bee = f"he{st}"
                if main[hive] > main[bee]:
                    main[bee] = main[hive]
                if perp[hive] > perp[bee]:
                    perp[bee] = perp[hive]

        return main, perp, gravity

    def define_constraint_function(self):
        """
        Constraint functions for identifying the combinations of all possible cross-sections
        We don't want to have a wacky building...
        Unique structural elements: 1. External columns in x and y directions, e.g h111
                                    2. All internal columns, e.g. h221
                                    3. External beams in x direction, e.g. bx111 x hx111
                                    4. External beams in y direction, e.g. by111 x hy111
                                    5. Internal beams in x direction, e.g. bx121 x hx121
                                    6. Internal beams in y direction, e.g. by211 x hy211
        :return: DataFrame                  All solutions with element cross-sections
        """
        # Number of bays
        nx = self.nbays_x
        ny = self.nbays_y

        # Helper constraint functions
        def equality(a, b):
            a = round(a, 2)
            b = round(b, 2)
            if a + 10**-5 >= b >= a - 10**-5:
                return True

        def storey_constraint(a, b):
            a = round(a, 2)
            b = round(b, 2)
            if a + 10**-5 >= b >= a - 0.05 - 10**-5:
                return True

        def bay_constraint(a, b):
            a = round(a, 2)
            b = round(b, 2)
            if self.reduce_combos:
                tol = 0.1
            else:
                tol = 0.2

            if b + tol + 10**-5 >= a >= b - 10**-5:
                return True

        def beam_constraint(a, b):
            a = round(a, 2)
            b = round(b, 2)
            if a + 0.1 - 10**-5 <= b <= a + 0.3 + 10**-5:
                return True

        # Initialize element types
        ele_types = []
        # Initialize the problem
        problem = constraint.Problem()

        # Add the elements into the variables list
        # Loop for each storey level
        for st in range(1, self.nst + 1):
            # Loop for each bay in x direction
            for x in range(1, nx + 2):
                # Loop for each bay in y direction
                for y in range(1, ny + 2):
                    # Add the variables
                    # Columns
                    problem.addVariable(f"h{x}{y}{st}", np.arange(0.35, 0.75, 0.05))
                    ele_types.append(f"h{x}{y}{st}")
                    # Beams along x direction
                    if x < nx + 1:
                        problem.addVariable(f"bx{x}{y}{st}", np.arange(0.35, 0.65, 0.05))
                        problem.addVariable(f"hx{x}{y}{st}", np.arange(0.45, 0.75, 0.05))
                        ele_types.append(f"bx{x}{y}{st}")
                        ele_types.append(f"hx{x}{y}{st}")
                    # Beams along y direction
                    if y < ny + 1:
                        problem.addVariable(f"by{x}{y}{st}", np.arange(0.35, 0.65, 0.05))
                        problem.addVariable(f"hy{x}{y}{st}", np.arange(0.45, 0.75, 0.05))
                        ele_types.append(f"by{x}{y}{st}")
                        ele_types.append(f"hy{x}{y}{st}")

        # Add constraints to cross-section dimensions
        # Constrain symmetry of building
        for st in range(1, self.nst + 1):
            # Constrain columns
            if not self.reduce_combos:
                # Group 1 constraints: Corner columns
                problem.addConstraint(equality, [f"h11{st}", f"h{nx+1}1{st}"])
                problem.addConstraint(equality, [f"h11{st}", f"h{nx+1}{ny+1}{st}"])
                problem.addConstraint(equality, [f"h11{st}", f"h1{ny+1}{st}"])
                # Group 2 constraints: Corner central columns x
                for x in range(2, int(nx / 2) + 2):
                    problem.addConstraint(equality, [f"h{x}1{st}", f"h{x}{ny+1}{st}"])
                    problem.addConstraint(equality, [f"h{x}1{st}", f"h{x+1}1{st}"])
                    problem.addConstraint(equality, [f"h{x}1{st}", f"h{x+1}{ny+1}{st}"])
                # Group 3 constraints: Corner central columns y
                for y in range(2, int(ny / 2) + 2):
                    problem.addConstraint(equality, [f"h1{y}{st}", f"h{nx+1}{y}{st}"])
                    problem.addConstraint(equality, [f"h1{y}{st}", f"h1{y+1}{st}"])
                    problem.addConstraint(equality, [f"h1{y}{st}", f"h{nx+1}{y+1}{st}"])
            else:
                # Group all corner columns
                hive = f"h11{st}"
                for x in range(1, nx + 2):
                    for y in range(1, ny + 2):
                        bee = f"h{x}{y}{st}"
                        if bee != hive and (x == 1 or y == 1 or x == nx + 1 or y == ny + 1):
                            problem.addConstraint(equality, [hive, bee])

            # Group 4 constraints: Central columns
            hive = f"h22{st}"
            for x in range(2, nx + 1):
                for y in range(2, ny + 1):
                    bee = f"h{x}{y}{st}"
                    if hive != bee:
                        problem.addConstraint(equality, [hive, bee])

            # Constrain beams
            if not self.reduce_combos:
                # Internal not necessarily equal to analysis
                # Corner beams along x
                hive = [f"bx11{st}", f"hx11{st}"]
                for x in range(1, nx + 1):
                    for y in [1, ny + 1]:
                        bee = [f"bx{x}{y}{st}", f"hx{x}{y}{st}"]
                        if hive[0] != bee[0]:
                            problem.addConstraint(equality, [hive[0], bee[0]])
                            problem.addConstraint(equality, [hive[1], bee[1]])
                # Corner beams along y
                hive = [f"by11{st}", f"hy11{st}"]
                for y in range(1, ny + 1):
                    for x in [1, nx + 1]:
                        bee = [f"by{x}{y}{st}", f"hy{x}{y}{st}"]
                        if hive[0] != bee[0]:
                            problem.addConstraint(equality, [hive[0], bee[0]])
                            problem.addConstraint(equality, [hive[1], bee[1]])
                # Central beams along x
                if ny > 1:
                    hive = [f"bx12{st}", f"hx12{st}"]
                    for x in range(1, nx + 1):
                        for y in range(2, ny + 1):
                            bee = [f"bx{x}{y}{st}", f"hx{x}{y}{st}"]
                            if hive[0] != bee[0]:
                                problem.addConstraint(equality, [hive[0], bee[0]])
                                problem.addConstraint(equality, [hive[1], bee[1]])
                # Central beams along y
                if nx > 1:
                    hive = [f"by21{st}", f"hy21{st}"]
                    for y in range(1, ny + 1):
                        for x in range(2, nx + 1):
                            bee = [f"by{x}{y}{st}", f"hy{x}{y}{st}"]
                            if hive[0] != bee[0]:
                                problem.addConstraint(equality, [hive[0], bee[0]])
                                problem.addConstraint(equality, [hive[1], bee[1]])
            else:
                # Beams along x, internal equal to analysis
                hive = [f"bx11{st}", f"hx11{st}"]
                for x in range(1, nx + 1):
                    for y in range(1, ny + 2):
                        bee = [f"bx{x}{y}{st}", f"hx{x}{y}{st}"]
                        if bee[0] != hive[0]:
                            problem.addConstraint(equality, [hive[0], bee[0]])
                            problem.addConstraint(equality, [hive[1], bee[1]])
                # Beams along y, internal equal to analysis
                hive = [f"by11{st}", f"hy11{st}"]
                for y in range(1, ny + 1):
                    for x in range(1, nx + 2):
                        bee = [f"by{x}{y}{st}", f"hy{x}{y}{st}"]
                        if bee[0] != hive[0]:
                            problem.addConstraint(equality, [hive[0], bee[0]])
                            problem.addConstraint(equality, [hive[1], bee[1]])

        # Constrain equality of beam and column sections by creating groups of 2 per storey
        for st in range(1, self.nst, 2):
            # If nst is odd, the last storey will be in a group of 1, so no equality constraint is applied
            for x in range(1, nx + 2):
                for y in range(1, ny + 2):
                    problem.addConstraint(equality, [f"h{x}{y}{st}", f"h{x}{y}{st+1}"])
                    if x < nx + 1:
                        problem.addConstraint(equality, [f"bx{x}{y}{st}", f"bx{x}{y}{st+1}"])
                        problem.addConstraint(equality, [f"hx{x}{y}{st}", f"hx{x}{y}{st+1}"])
                    if y < ny + 1:
                        problem.addConstraint(equality, [f"by{x}{y}{st}", f"by{x}{y}{st+1}"])
                        problem.addConstraint(equality, [f"hy{x}{y}{st}", f"hy{x}{y}{st+1}"])

            # Force allowable variations of c-s dimensions between elements of adjacent groups
            if st <= self.nst - 2:
                for x in range(1, nx + 2):
                    for y in range(1, ny + 2):
                        problem.addConstraint(storey_constraint, [f"h{x}{y}{st}", f"h{x}{y}{st+2}"])
                        if x < nx + 1:
                            problem.addConstraint(storey_constraint, [f"bx{x}{y}{st}", f"bx{x}{y}{st+2}"])
                            problem.addConstraint(storey_constraint, [f"hx{x}{y}{st}", f"hx{x}{y}{st+2}"])
                        if y < ny + 1:
                            problem.addConstraint(storey_constraint, [f"by{x}{y}{st}", f"by{x}{y}{st+2}"])
                            problem.addConstraint(storey_constraint, [f"hy{x}{y}{st}", f"hy{x}{y}{st+2}"])

        # Constrain beam width equal to analysis column heights connecting the beam
        for st in range(1, self.nst + 1):
            # Along x
            for y in range(1, ny + 2):
                problem.addConstraint(equality, [f"bx1{y}{st}", f"h1{y}{st}"])
            # Along y
            for x in range(1, nx + 2):
                problem.addConstraint(equality, [f"by{x}1{st}", f"h{x}1{st}"])

        # Constrain allowable variation of beam cross-section width and height
        for st in range(1, self.nst + 1):
            for x in range(1, nx + 2):
                for y in range(1, ny + 2):
                    if x < nx + 1:
                        problem.addConstraint(beam_constraint, [f"bx{x}{y}{st}", f"hx{x}{y}{st}"])
                    if y < ny + 1:
                        problem.addConstraint(beam_constraint, [f"by{x}{y}{st}", f"hy{x}{y}{st}"])

        # Constrain beam cross-sections to be equal on a straight line (along each axis)
        # Beams along x axis
        for st in range(1, self.nst + 1):
            for y in range(1, ny + 2):
                hive = [f"bx1{y}{st}", f"hx1{y}{st}"]
                for x in range(2, nx + 1):
                    bee = [f"bx{x}{y}{st}", f"hx{x}{y}{st}"]
                    problem.addConstraint(equality, [hive[0], bee[0]])
                    problem.addConstraint(equality, [hive[1], bee[1]])

        # Beams along y axis
        for st in range(1, self.nst + 1):
            for x in range(1, nx + 2):
                hive = [f"by{x}1{st}", f"hy{x}1{st}"]
                for y in range(2, ny + 1):
                    bee = [f"by{x}{y}{st}", f"hy{x}{y}{st}"]
                    problem.addConstraint(equality, [hive[0], bee[0]])
                    problem.addConstraint(equality, [hive[1], bee[1]])

        # Constrain variation of column cross-sections along x and y (neighbors, analysis vs internal)
        for st in range(1, self.nst + 1):
            # Along x direction
            for y in range(1, ny + 2):
                external = f"h1{y}{st}"
                if nx > 1:
                    internal = f"h2{y}{st}"
                    problem.addConstraint(bay_constraint, [internal, external])
            # Along y direction
            for x in range(1, nx + 2):
                external = f"h{x}1{st}"
                if ny > 1:
                    internal = f"h{x}2{st}"
                    problem.addConstraint(bay_constraint, [internal, external])

        # Find all possible solutions within the constraints specified
        solutions = problem.getSolutions()

        success_msg(f"Number of solutions found: {len(solutions)}")

        elements = np.zeros((len(solutions), len(ele_types)))
        cnt = 0
        for ele in ele_types:
            for index, solution in enumerate(solutions):
                elements[index][cnt] = solution[ele]
            cnt += 1
        elements = np.unique(elements, axis=0)
        elements = pd.DataFrame(elements, columns=ele_types)

        return elements

    def get_weight(self, props):
        """
        gets structural weight of a solution
        :param props: DataFrame                                 Cross-section dimensions of the structural elements
        :return: float                                          Weight of the structural system
        """
        spans_x = self.data.spans_x
        spans_y = self.data.spans_y
        heights = self.data.heights
        w = 0
        for st in range(1, self.nst + 1):
            for x in range(1, self.nbays_x + 2):
                for y in range(1, self.nbays_y + 2):
                    # Add weight of columns (square columns only)
                    w += self.SELF_WEIGHT * props[f"h{x}{y}{st}"] ** 2 * heights[st - 1]
                    # Add weight of beams along x
                    if x < self.nbays_x + 1:
                        w += self.SELF_WEIGHT * props[f"bx{x}{y}{st}"] * props[f"hx{x}{y}{st}"] * spans_x[x - 1]
                    # Add weight of beams along y
                    if y < self.nbays_y + 1:
                        w += self.SELF_WEIGHT * props[f"by{x}{y}{st}"] * props[f"hy{x}{y}{st}"] * spans_y[y - 1]

        return w

    def find_optimal_solution(self, solution=None):
        """
        finds optimal solution based on minimizing weight
        :param solution: Series                                 Solution to run analysis instead (for iterations)
        :return optimal: Series                                 Optimal solution based on minimizing weight
        :return opt_modes: dict                                 Periods and normalized modal shapes of the optimal
                                                                solution
        """
        if solution is None:
            # A new approach to take the case with lowest period, from the loop of cases with lowest weight
            # It tries to ensure that the actual period will be at a more tolerable range
            solutions = self.solutions.nsmallest(20, "Weight")
            optimal = solutions[solutions["T1"] == solutions["T1"].min()].iloc[0]
        else:
            if isinstance(solution, int):
                # ID of solution has been provided, select from existing dataframe by index
                optimal = self.solutions.loc[solution]
            else:
                optimal = solution
                if isinstance(optimal, pd.DataFrame):
                    optimal = optimal.iloc[solution.first_valid_index()]

        cs = self.get_section(optimal)

        # Run modal analysis via OpenSeesPy
        hinge = {"x_seismic": None, "y_seismic": None, "gravity": None}
        op = OpenSeesRun(self.data, cs, self.fstiff, system="space", hinge=hinge)
        op.create_model()
        op.define_masses()
        num_modes = self.nst if self.nst <= 9 else 9
        periods, modalShape, gamma, mstar = op.run_modal_analysis(num_modes)
        op.wipe()

        weight = self.get_weight(optimal)
        optimal["T1"] = periods[0]
        optimal["T2"] = periods[1]
        optimal["Weight"] = weight
        optimal["Mstar1"] = mstar[0]
        optimal["Mstar2"] = mstar[1]
        optimal["Part Factor1"] = abs(gamma[0])
        optimal["Part Factor2"] = abs(gamma[1])

        opt_modes = {"Periods": periods, "Modes": modalShape}
        return optimal, opt_modes
