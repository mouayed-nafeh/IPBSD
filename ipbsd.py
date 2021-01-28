"""
Runs the master file for Integrated Performance-Based Seismic Design (IPBSD)
"""
import timeit
import os
import json
import pandas as pd
import numpy as np
import pickle
from client.master import Master
from client.iterations import Iterations
from pathlib import Path


class IPBSD:
    def __init__(self, input_file, hazard_file, slfDir, spo_file, limit_eal, target_mafc, outputPath, analysis_type=1,
                 damping=.05, num_modes=3, iterate=False, system="Perimeter", maxiter=20, fstiff=0.5, rebar_cover=0.03,
                 flag3d=False, solutionFileX=None, solutionFileY=None, export_cache=False, holdFlag=False,
                 overstrength=None, replCost=None):
        """
        Initializes IPBSD
        :param input_file: str              Input filename as '*.csv'
        :param hazard_file: str             Hazard filename as '*.pkl' or '*.pickle'
        :param slfDir: str                  Directory of SLFs derived via SLF Generator
        :param spo_file: str                SPO filename '*.csv'
        :param limit_eal: float             Liming value of EAL
        :param target_mafc: float           Target value of MAFC
        :param outputPath: str              Outputs path (where to store the outputs)
        :param analysis_type: int           Analysis type:
                                            1: Simplified ELF - no analysis is run, calculations based on
                                            simplified expressions, actions based on 1st mode shape (default)
                                            2: ELF - equivalent lateral force method of analysis, actions based on
                                            1st mode shape
                                            3: ELF & gravity - analysis under ELF and gravity loads
                                            4: RMSA - response method of spectral analysis, actions based on "n" modal
                                            shapes
                                            5: RMSA & gravity - analysis under RMSA and gravity loads
        :param damping: float               Ratio of critical damping
        :param num_modes: int               Number of modes to consider for SRSS (for analysis type 4 and 5)
        :param iterate: bool                Perform iterations or not (refers to iterations 4a and 3a)
        :param system: str                  Structural system of the building (Perimeter or Space)
        :param maxiter: int                 Maximum number of iterations for seeking a solution
        :param fstiff: float                Stiffness reduction factor
        :param rebar_cover: float           Reinforcement cover in m
        :param flag3d: str                  True if 3D building is being considered (runs IPBSD in both directions)
        :param solutionFileX: str           Path to solution file to be used for design in dir1 (X direction)
        :param solutionFileY: str           Path to solution file to be used for design in dir2 (Y direction)
                                            (optional: not necessary if flag3d is False)
        :param export_cache: bool           Whether to export cache at each major step into an outputs directory or not
        :param holdFlag: bool               Flag to stop the framework once the solution combinations have been computed
                                            This allows the user to subdivide the framework into two sections if it
                                            takes too long to find a solution. Alternatively, if holdFlag is False,
                                            full framework will be run, and if solution.csv at the outputDir already
                                            exists, then the framework will skip the step of its derivation.
                                            holdFlag=False makes sense if the framework has already generated the csv
                                            file containing all valid solutions.
        :param overstrength: float          Overstrength ratio, leave on default and the user will automatically assign
                                            a value
        :param replCost: float              Replacement cost of the entire building
        """
        self.dir = Path.cwd()
        self.input_file = input_file
        self.hazard_file = hazard_file
        self.slfDir = slfDir
        self.spo_file = spo_file
        self.limit_EAL = limit_eal
        self.target_MAFC = target_mafc
        self.outputPath = outputPath
        self.analysis_type = analysis_type
        self.num_modes = num_modes
        self.damping = damping
        self.iterate = iterate
        self.system = system                # TODO, currently does nothing, IPBSD is only working with Perimeter frames, Space (loads etc. to be updated) frames to be added
        self.maxiter = maxiter
        self.fstiff = fstiff
        self.rebar_cover = rebar_cover
        self.solutionFileX = solutionFileX
        self.solutionFileY = solutionFileY
        self.export_cache = export_cache
        self.holdFlag = holdFlag
        self.overstrength = overstrength
        self.replCost = replCost

        # 2d (False) means, that even if the SLFs are provided for the entire building, only 1 direction
        # (defaulting to dir1) will be considered. This also entails the use of non-dimensional components,
        # however, during loss assessment the non-dimensional factor will not be applied (i.e. nd_factor=1.0)
        self.flag3d = flag3d

        if self.export_cache:
            # Create a folder for 'Cache' if none exists
            self.create_folder(self.outputPath / "Cache")

    @staticmethod
    def get_init_time():
        """
        Records initial time
        :return: float                      Initial time
        """
        start_time = timeit.default_timer()
        return start_time

    @staticmethod
    def truncate(n, decimals=0):
        """
        Truncates time with given decimal points
        :param n: float                     Time
        :param decimals: int                Decimal points
        :return: float                      Truncated time
        """
        multiplier = 10 ** decimals
        return int(n * multiplier) / multiplier

    def get_time(self, start_time):
        """
        Prints running time in seconds and minutes
        :param start_time: float            Initial time
        :return: None
        """
        elapsed = timeit.default_timer() - start_time
        print('Running time: ', self.truncate(elapsed, 1), ' seconds')
        print('Running time: ', self.truncate(elapsed / float(60), 2), ' minutes')

    def create_folder(self, directory):
        """
        creates directory
        :param directory: str                   Directory to be created
        :return: None
        """
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
        except OSError:
            print("Error: Creating directory. " + directory)

    def export_results(self, filepath, data, filetype):
        """
        Store results in the database
        :param filepath: str                            Filepath, e.g. "directory/name"
        :param data:                                    Data to be stored
        :param filetype: str                            Filetype, e.g. npy, json, pkl, csv
        :return: None
        """
        if filetype == "npy":
            np.save(f"{filepath}.npy", data)
        elif filetype == "pkl" or filetype == "pickle":
            with open(f"{filepath}.pickle", 'wb') as handle:
                pickle.dump(data, handle)
        elif filetype == "json":
            with open(f"{filepath}.json", "w") as json_file:
                json.dump(data, json_file)
        elif filetype == "csv":
            data.to_csv(f"{filepath}.csv", index=False)

    def cacheRCMRF(self, ipbsd, details, sol, demands):
        """
        Creates cache to be used by RCMRF
        :param ipbsd: object                            Master class
        :param details: dict                            Details of design
        :param sol: dict                                Optimal solution
        :param demands: dict                            Demands on structural components
        :return: None
        """
        # Loads
        floorLoad = ipbsd.data.i_d["bldg_ch"][0]
        roofLoad = ipbsd.data.i_d["bldg_ch"][1]
        area = ipbsd.data.i_d["bldg_ch"][2]

        nst = len(ipbsd.data.i_d["h_storeys"])
        nGravity = int(ipbsd.data.i_d["n_gravity_frames"][0])
        nSeismic = int(ipbsd.data.i_d["n_seismic_frames"][0])

        spansX = np.array([ipbsd.data.i_d["spans_X"][x] for x in ipbsd.data.i_d["spans_X"]])
        spansY = np.array([ipbsd.data.i_d["spans_Y"][x] for x in ipbsd.data.i_d["spans_Y"]])
        heights = np.array([ipbsd.data.i_d["h_storeys"][x] for x in ipbsd.data.i_d["h_storeys"]])

        X = sum(spansX)
        Y = sum(spansY)

        if self.flag3d:
            # Along X direction
            f_loads = []
            r_loads = []
            for x in spansX:
                if x <= spansY[0]:
                    f_loads.append(floorLoad * x**2 / 4)
                    r_loads.append(roofLoad * x**2 / 4)
                else:
                    f_loads.append(1/4 * floorLoad * spansY[0] * (2 * x - spansY[0]))
                    r_loads.append(1/4 * roofLoad * spansY[0] * (2 * x - spansY[0]))

            # Along Y direction
            f_loads = []
            r_loads = []
            for y in spansY:
                if y <= spansX[0]:
                    f_loads.append(floorLoad * y**2 / 4)
                    r_loads.append(roofLoad * y**2 / 4)
                else:
                    f_loads.append(1/4 * floorLoad * spansX[0] * (2 * y - spansX[0]))
                    r_loads.append(1/4 * roofLoad * spansX[0] * (2 * y - spansX[0]))

            # Assuming uniform distribution (not quite precise)
            dist_x = [sum(f_loads) / sum(spansX), sum(r_loads) / sum(spansX)]
            dist_y = [sum(f_loads) / sum(spansY), sum(r_loads) / sum(spansY)]
            distLoads = [dist_x, dist_y]

        else:
            if self.system == "Perimeter":
                distLength = spansY[0] / 2
            else:
                distLength = spansY[0]

            # Distributed loads
            distLoads = [floorLoad * distLength, roofLoad * distLength]

        # Point loads, for now will be left as zero
        pLoads = 0.0

        # PDelta loads/ essentially loads going to the gravity frames
        if nGravity > 0:
            pDeltaLoad = ipbsd.data.pdelta_loads
        else:
            pDeltaLoad = 0.0

        # Masses (actual frame mass is exported)
        masses = np.array(ipbsd.data.masses)

        # Creating a DataFrame for loads
        loads = pd.DataFrame(columns=["Storey", "Pattern", "Load"])

        for st in range(1, nst + 1):
            if self.flag3d:
                lx = distLoads[0][1] if st == nst else distLoads[0][0]
                ly = distLoads[1][1] if st == nst else distLoads[1][0]
            else:
                lx = distLoads[1] if st == nst else distLoads[0]
                ly = 0.0

            loads = loads.append({"Storey": st,
                                  "Pattern": "distributed",
                                  "Load": lx}, ignore_index=True)
            if self.flag3d:
                loads = loads.append({"Storey": st,
                                      "Pattern": "distributed_y",
                                      "Load": ly}, ignore_index=True)

            # Point loads will be left as zeros for now
            loads = loads.append({"Storey": st,
                                  "Pattern": "point internal",
                                  "Load": pLoads}, ignore_index=True)
            loads = loads.append({"Storey": st,
                                  "Pattern": "point external",
                                  "Load": pLoads}, ignore_index=True)

            # PDelta loads
            if nGravity > 0:
                lx = pDeltaLoad[st-1] / ipbsd.data.n_seismic
                loads = loads.append({"Storey": st,
                                      "Pattern": "pdelta",
                                      "Load": lx}, ignore_index=True)
            else:
                loads = loads.append({"Storey": st,
                                      "Pattern": "pdelta",
                                      "Load": pDeltaLoad}, ignore_index=True)

            # Masses
            loads = loads.append({"Storey": st,
                                  "Pattern": "mass",
                                  "Load": masses[st - 1] / ipbsd.data.n_seismic}, ignore_index=True)

        # Exporting action for use by a Modeler module
        # TODO - fix load distributions
        """
        For a two-way slab assumption, load distribution will not be uniform.
        For now and for simplicity, total load over each directions is computed and then divided by global length to 
        assume a uniform distribution. """
        self.export_results(self.outputPath / "action", loads, "csv")

        # Materials
        fc = ipbsd.data.i_d["fc"][0]
        fy = ipbsd.data.i_d["fy"][0]
        Es = ipbsd.data.i_d["Es"][0]

        # Elastic modulus of uncracked concrete
        Ec = (3320 * np.sqrt(fc) + 6900) * self.fstiff

        materials = pd.DataFrame({"fc": fc,
                                  "fy": fy,
                                  "Es": Es,
                                  "Ec": Ec}, index=[0])

        # Exporting the materials file for use by a Modeler module
        self.export_results(self.outputPath / "materials", materials, "csv")

        """Section properties (for the Haselton model)"""
        def get_sections(i, sections, details, sol, demands, ele, iterator, st, bay, nbays, bayName):
            eleType = "Beam" if ele == "Beams" else "Column"
            pos = "External" if bay == 1 else "Internal"
            p0 = pos[0].lower() if eleType == "Column" else ""

            # C-S dimensions
            if eleType == "Beam":
                b = sol.loc[f"b{st}"]
                h = sol.loc[f"h{st}"]
                Ptotal = 0.0
                length = spansX[bay - 1]
                MyPos = details[ele]["Pos"][i][3]["yield"]["moment"]
                MyNeg = details[ele]["Neg"][i][3]["yield"]["moment"]
                coverPos = details[ele]["Pos"][i][0]["cover"]
                coverNeg = details[ele]["Neg"][i][0]["cover"]
                roPos = details[ele]["Pos"][i][0]["reinforcement"] / (b * (h - coverPos))
                roNeg = details[ele]["Neg"][i][0]["reinforcement"] / (b * (h - coverNeg))

            else:
                b = h = sol.loc[f"h{p0}{st}"]
                Ptotal = max(demands[ele]["N"][st - 1][bay - 1], demands[ele]["N"][st - 1][nbays - bay + 1], key=abs)
                length = heights[st - 1]
                MyPos = MyNeg = details[ele][i][3]["yield"]["moment"]
                coverPos = coverNeg = details[ele][i][0]["cover"]
                roPos = roNeg = details[ele][i][0]["reinforcement"] / (b * (h - coverPos))

            # Residual strength of component
            res = iterator[i][3]["fracturing"]["moment"] / iterator[i][3]["yield"]["moment"]

            # Appending into the DataFrame
            sections = sections.append({"Element": eleType,
                                        "Bay": bayName,
                                        "Storey": st,
                                        "Position": pos,
                                        "b": float(b),
                                        "h": float(h),
                                        "coverPos": float(coverPos),
                                        "coverNeg": float(coverNeg),
                                        "Ptotal": Ptotal,
                                        "MyPos": float(MyPos),
                                        "MyNeg": float(MyNeg),
                                        "asl": asl,
                                        "Ash": float(iterator[i][0]["A_sh"]),
                                        "spacing": float(iterator[i][0]["spacing"]),
                                        "db": db,
                                        "c": c,
                                        "D": D,
                                        "Res": float(res),
                                        "Length": length,
                                        "ro_long_pos": float(roPos),
                                        "ro_long_neg": float(roNeg)}, ignore_index=True)
            return sections

        # Constants - assumptions - to be made more flexible
        asl = 0
        c = 1
        D = 1
        db = 20
        nbays = len(spansX)

        # Initialize sections
        sections = pd.DataFrame(columns=["Element", "Bay", "Storey", "Position", "b", "h", "coverPos", "coverNeg",
                                         "Ptotal", "MyPos", "MyNeg", "asl", "Ash", "spacing", "db", "c", "D", "Res",
                                         "Length", "ro_long_pos", "ro_long_neg"])

        for ele in details:
            if ele == "Beams":
                iterator = details[ele]["Pos"]
            else:
                iterator = details[ele]

            for i in iterator:
                st = int(i[1])
                bay = int(i[3])
                sections = get_sections(i, sections, details, sol, demands, ele, iterator, st, bay, nbays, bayName=bay)

        # Add symmetric columns
        if bay < nbays:
            bayName = bay
            for bb in range(nbays - bay + 1, 0, -1):
                bayName += 1
                for st in range(1, nst + 1):
                    ele = "Columns"
                    i = f"S{st}B{bb}"
                    iterator = details[ele]
                    sections = get_sections(i, sections, details, sol, demands, ele, iterator, st, bb, nbays, bayName)

            bayName = bay
            for bb in range(nbays - bay, 0, -1):
                bayName += 1
                for st in range(1, nst + 1):
                    ele = "Beams"
                    i = f"S{st}B{bb}"
                    iterator = details[ele]["Pos"]
                    sections = get_sections(i, sections, details, sol, demands, ele, iterator, st, bb, nbays, bayName)

        # Exporting the sections file for use by Modeler module as Haselton springs
        self.export_results(self.outputPath / "haselton_springs", sections, "csv")

    def check_file(self, path):
        """
        Checks if DataFrame in path exists and returns it
        :param path: str
        :return: DataFrame
        """

        if path is not None:
            try:
                df = pd.read_csv(path)
            except:
                df = None
        else:
            df = None
        return df

    def run_ipbsd(self):

        """Calling the master file"""
        ipbsd = Master(self.dir, flag3d=self.flag3d)

        """Generating and storing the input arguments"""
        ipbsd.read_input(self.input_file, self.hazard_file, self.outputPath)
        # Initiate {project name}
        print(f"[INITIATE] Starting IPBSD for {ipbsd.data.case_id}")

        print("[PHASE] Commencing phase 1...")
        self.create_folder(self.outputPath)
        ipbsd.data.i_d["MAFC"] = self.target_MAFC
        ipbsd.data.i_d["EAL"] = self.limit_EAL
        # Store IPBSD inputs as a json
        if self.export_cache:
            self.export_results(self.outputPath / "Cache/input_cache", ipbsd.data.i_d, "json")
        print("[SUCCESS] Input arguments have been read and successfully stored")

        # """Get EAL"""
        lam_ls = ipbsd.get_hazard_pga(self.target_MAFC)
        eal, y_fit, lam_fit = ipbsd.get_loss_curve(lam_ls, self.limit_EAL)
        lossCurve = {"y": ipbsd.data.y, "lam": lam_ls, "y_fit": y_fit, "lam_fit": lam_fit, "eal": eal,
                     "PLS": ipbsd.data.PLS}
        print(f"[SUCCESS] EAL = {eal:.2f}")

        """Get design limits"""
        theta_max, a_max, slfsCache = ipbsd.get_design_values(self.slfDir, self.replCost)
        if self.export_cache:
            self.export_results(self.outputPath / "Cache/SLFs", slfsCache, "pickle")
        print("[SUCCESS] SLF successfully read, and design limits are calculated")

        """Transform design values into spectral coordinates"""
        tables, delta_spectral, alpha_spectral = ipbsd.perform_transformations(theta_max, a_max)
        if self.export_cache:
            self.export_results(self.outputPath / "Cache/table_sls", tables, "pickle")
        print("[SUCCESS] Spectral values of design limits are obtained")

        """Get spectra at SLS"""
        print("[PHASE] Commencing phase 2...")
        sa, sd, period_range = ipbsd.get_spectra(lam_ls[1])
        if self.export_cache:
            i = sa.shape[0]
            sls_spectrum = np.concatenate((period_range.reshape(i, 1), sd.reshape(i, 1), sa.reshape(i, 1)), axis=1)
            sls_spectrum = pd.DataFrame(data=sls_spectrum, columns=["Period", "Sd", "Sa"])
            self.export_results(self.outputPath / "Cache/sls_spectrum", sls_spectrum, "csv")

        print("[SUCCESS] Response spectra generated")

        """Get feasible fundamental period range"""
        if method.flag3d:
            period_limits = {"1": [], "2": []}
        else:
            period_limits = {"1": []}

        for i in range(delta_spectral.shape[0]):
            t_lower, t_upper = ipbsd.get_period_range(delta_spectral[i], alpha_spectral[i], sd, sa)
            period_limits[str(i + 1)] = [t_lower, t_upper]
            print(f"[SUCCESS] Feasible period range identified. T_lower = {t_lower:.2f}s, T_upper = {t_upper:.2f}s")

        """Get all section combinations satisfying period bound range
        Notes: If solutions cache exists in outputs directory, the file will be read and an optimal solution based on
        least weight will be derived.
        If solutions cache does not exist, then a solutions file will be created (may take some time) and then the
        optimal solution is derived.
        If an optimal solution is provided, then eigenvalue analysis is performed for the
        optimal solution. No solutions cache will be derived.
        """
        # Check whether solutions file was provided
        solution_x = self.check_file(self.solutionFileX)
        solution_y = self.check_file(self.solutionFileY)

        results = ipbsd.get_all_section_combinations(period_limits, fstiff=self.fstiff,
                                                     cache_dir=self.outputPath/"Cache",
                                                     solution_x=solution_x, solution_y=solution_y)
        print("[SUCCESS] All section combinations were identified")

        # Call the iterations function (iterations have not yet started though)
        if method.flag3d:
            # 3D option
            frames = 2
        else:
            # 2D option
            frames = 1

        # The main portion of IPBSD is completed. Now corrections should be made for the assumptions
        if not self.holdFlag:

            for i in range(frames):
                if i == 0:
                    print("[INITIATE] Designing frame in X direction!")
                elif i == 1:
                    print("[INITIATE] Designing frame in Y direction!")

                sols = results[i]["sols"]
                opt_sol = results[i]["opt_sol"]
                opt_modes = results[i]["opt_modes"]
                t_lower, t_upper = period_limits[str(i + 1)]
                table_sls = tables[i]

                if self.flag3d:
                    if i == 0:
                        gravity_loads = ipbsd.data.loads_x
                    else:
                        gravity_loads = ipbsd.data.loads_y
                else:
                    gravity_loads = ipbsd.data.w_seismic

                # Call the iterations function (iterations have not yet started though)
                iterations = Iterations(ipbsd, sols, self.spo_file, self.target_MAFC, self.analysis_type, self.damping,
                                        self.num_modes, self.fstiff, self.rebar_cover, self.outputPath,
                                        gravity_loads=gravity_loads, direction=i)

                # Run the validations and iterations if need be
                ipbsd_outputs, spoResults, opt_sol, demands, details, hinge_models, action, modelOutputs = \
                    iterations.validations(opt_sol, opt_modes, sa, period_range, table_sls, t_lower, t_upper,
                                           self.iterate, self.maxiter, omega=self.overstrength)

                """Iterations are completed and IPBSD is finalized"""
                # Export main outputs and cache
                if self.export_cache:
                    """Storing the outputs"""
                    # Exporting the IPBSD outputs
                    self.create_folder(self.outputPath / f"Cache/frame{i+1}")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/spoShape",
                                        pd.DataFrame(iterations.spo_shape, index=[0]), "csv")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/lossCurve", lossCurve, "pickle")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/spoAnalysisCurveShape", spoResults,
                                        "pickle")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/optimal_solution", opt_sol, "csv")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/action", action, "csv")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/demands", demands, "pkl")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/ipbsd", ipbsd_outputs, "pkl")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/details", details, "pkl")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/hinge_models", hinge_models, "csv")
                    self.export_results(self.outputPath / f"Cache/frame{i+1}/modelOutputs", modelOutputs, "pickle")

                    """Creating DataFrames to store for RCMRF input"""
                    self.cacheRCMRF(ipbsd, details, opt_sol, demands)

                print("[SUCCESS] Structural elements were designed and detailed. SPO curve parameters were estimated")
                # Note: stiffness based off first yield point, at nominal point the stiffness is actually lower, and
                # might act as a more realistic value. Notably Haselton, 2016 limits the secant yield stiffness between
                # 0.2EIg and 0.6EIg.

                print("[END] IPBSD was performed successfully")


if __name__ == "__main__":

    """
    :param analysis_type: int                   Analysis type:
                                                1: Simplified ELF - no analysis is run, calculations based on 
                                                simplified expressions
                                                2: ELF - equivalent lateral force method of analysis
                                                3: ELF & gravity - analysis under ELF and gravity loads
                                                4: RMSA - response method of spectral analysis
                                                5: RMSA & gravity - analysis under RMSA and gravity loads
    :param input_file: str                      Input file as '*.csv'
    :param hazard_file: str                     Hazard file as '*.pkl' or '*.pickle'
    :param slf_file: str                        File containing SLF curves as '*.xlsx'
    :param spo_file: str                        File containing SPO curve assumptions as '*.csv'
    :param limit_eal: float                     Limit EAL performance objective
    :param mafc_target: float                   MAFC target performance objective
    :param damping: float                       Damping (e.g. 0.05)
    :param system: str                          Lateral load resisting system type (Perimeter or Space)
    :param maxiter: int                         Maximum number of iterations for detailing optimization
    :param fstiff: float                        Section stiffness reduction factor
    """
    # Paths
    path = Path.cwd()
    outputPath = path.parents[0] / ".applications/LOSS Validation Manuscript/Case2"

    # Add input arguments
    analysis_type = 3
    input_file = path.parents[0] / ".applications/LOSS Validation Manuscript/Case2/ipbsd_input.csv"
    hazard_file = path.parents[0] / ".applications/LOSS Validation Manuscript/Hazard/Hazard-LAquila-Soil-C.pkl"
    slfDir = outputPath / "slfoutput"
    spo_file = path.parents[0] / ".applications/LOSS Validation Manuscript/Case2/spo.csv"
    limit_eal = 1.0
    mafc_target = 2.e-4
    damping = .05
    system = "Perimeter"
    maxiter = 2
    fstiff = 0.5
    overstrength = 1.0
    flag3d = True
    export_cache = True
    holdFlag = False
    iterate = True
    replCost = 349459.2 * 2

    # Design solution to use (leave None, if the tool needs to look for the solution)
    # solutionFile = path.parents[0] / ".applications/case1/designSol.csv"
    solutionFileX = None
    solutionFileY = None

    method = IPBSD(input_file, hazard_file, slfDir, spo_file, limit_eal, mafc_target, outputPath, analysis_type,
                   damping=damping, num_modes=2, iterate=iterate, system=system, maxiter=maxiter, fstiff=fstiff,
                   flag3d=flag3d, solutionFileX=solutionFileX, solutionFileY=solutionFileY, export_cache=export_cache,
                   holdFlag=holdFlag, overstrength=overstrength, rebar_cover=0.03, replCost=replCost)
    start_time = method.get_init_time()
    method.run_ipbsd()
    method.get_time(start_time)
