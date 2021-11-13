from src.master import Master
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
import pickle
from analysis.getT1 import GetT1
import json
import sys


def export_results(filepath, data, filetype):
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


def spectra_par(soil, type_spectra, damping):
    eta = max(np.sqrt(10 / (5 + damping * 100)), 0.55)
    if type_spectra == 1:
        if soil == 'A':
            S = 1.0
            Tb = 0.15
            Tc = 0.4
            Td = 2.
        if soil == 'B':
            S = 1.2
            Tb = 0.15
            Tc = 0.5
            Td = 2.
        if soil == 'C':
            S = 1.15
            Tb = 0.2
            Tc = 0.6
            Td = 2.
        if soil == 'D':
            S = 1.35
            Tb = 0.2
            Tc = 0.8
            Td = 2.
        if soil == 'F':
            S = 1.4
            Tb = 0.15
            Tc = 0.5
            Td = 2.
    if type_spectra == 2:
        if soil == 'A':
            S = 1.0
            Tb = 0.05
            Tc = 0.25
            Td = 1.2
        if soil == 'B':
            S = 1.35
            Tb = 0.05
            Tc = 0.25
            Td = 1.2
        if soil == 'C':
            S = 1.5
            Tb = 0.1
            Tc = 0.25
            Td = 1.2
        if soil == 'D':
            S = 1.8
            Tb = 0.1
            Tc = 0.3
            Td = 1.2
        if soil == 'F':
            S = 1.6
            Tb = 0.05
            Tc = 0.25
            Td = 1.2
    return S, Tb, Tc, Td, eta


def get_ECelastic_spectra(PGA, soil_class, type_spectra=1, damping=0.05):
    # elastic RS EC8 3.2.2.2
    # Type 1 spectra
    global S, Tb, Tc, Td, eta
    S, Tb, Tc, Td, eta = spectra_par(soil_class, type_spectra, damping)
    T = np.linspace(0., 4., 401)
    # Sa in g, Sd in cm
    Sa = np.array([])
    Sd = np.array([])
    for i in range(len(T)):
        if T[i] <= Tb:
            Sa = np.append(Sa, (PGA * S * (1 + T[i] / Tb * (eta * 2.5 - 1))))
        elif Tb < T[i] <= Tc:
            Sa = np.append(Sa, (PGA * S * eta * 2.5))
        elif Tc < T[i] <= Td:
            Sa = np.append(Sa, (PGA * S * eta * 2.5 * Tc / T[i]))
        elif Td < T[i] <= 4:
            Sa = np.append(Sa, (PGA * S * eta * 2.5 * Tc * Td / T[i] ** 2))
        else:
            print('Wrong period range!')
        Sd = np.append(Sd, (Sa[i] * 9.81 * T[i] ** 2 / 4 / np.pi ** 2 * 100))
    return T, Sa


def get_ECdesign_spectra(PGA, soil_class, q, type_spectra=1, damping=0.05, beta=0.2):
    # elastic RS EC8 3.2.2.2
    # Type 1 spectra
    global S, Tb, Tc, Td, eta
    S, Tb, Tc, Td, eta = spectra_par(soil_class, type_spectra, damping)
    T = np.linspace(0., 4., 401)
    # Sa in g, Sd in cm
    Sa = np.array([])
    Sd = np.array([])
    for i in range(len(T)):
        if T[i] <= Tb:
            Sa = np.append(Sa, (PGA * S * (2 / 3 + T[i] / Tb * (2.5 / q - 2 / 3))))
        elif Tb < T[i] <= Tc:
            Sa = np.append(Sa, (PGA * S * 2.5 / q))
        elif Tc < T[i] <= Td:
            Sa = np.append(Sa, (max(beta * PGA, PGA * S * 2.5 / q * Tc / T[i])))
        elif Td < T[i] <= 4:
            Sa = np.append(Sa, (max(beta * PGA, PGA * S * 2.5 / q * Tc * Td / T[i] ** 2)))
        else:
            print('Wrong period range!')
        Sd = np.append(Sd, (Sa[i] * 9.81 * T[i] ** 2 / 4 / np.pi ** 2 * 100))
    return T, Sa


def _hazard(coef, TR, beta_al):
    x = np.linspace(0.005, 3.0, 201)
    k0 = coef['k0']
    k1 = coef['k1']
    k2 = coef['k2']

    # Ground shaking MAFE
    H = 1 / TR
    p = 1 / (1 + 2 * k2 * (beta_al ** 2))
    Hs = float(k0) * np.exp(-float(k2) * np.log(x) ** 2 - float(k1) * np.log(x))
    MAF = np.sqrt(p) * k0 ** (1 - p) * Hs ** p * np.exp(0.5 * p * k1 ** 2 * (beta_al ** 2))
    p = 1 / (1 + 2 * k2 * (np.power(beta_al, 2)))
    lambdaLS = np.sqrt(p) * k0 ** (1 - p) * H ** p * np.exp(0.5 * p * np.power(k1, 2) * (np.power(beta_al, 2)))
    PGA = np.exp((-k1 + np.sqrt(k1 ** 2 - 4 * k2 * np.log(lambdaLS / k0))) / 2 / k2)
    return lambdaLS, PGA, MAF, x


def getIndex(x, data):
    if np.where(data >= x)[0].size == 0:
        return np.nan
    else:
        return np.where(data >= x)[0][0]


def get_critical_designs(hinge_models_x, hinge_models_y):
    """
    Modify hinge elements of analysis seismic columns to the strongest (larger My) from designs of both directions
    :param hinge_models_x:
    :param hinge_models_y:
    :return:
    """
    external_hinges_x = hinge_models_x[(hinge_models_x["Position"] == "analysis") &
                                       (hinge_models_x["Element"] == "Column")].reset_index()
    external_hinges_y = hinge_models_y[(hinge_models_y["Position"] == "analysis") &
                                       (hinge_models_y["Element"] == "Column")].reset_index()

    for index, row in external_hinges_x.iterrows():
        my_x = external_hinges_x["m1"].iloc[index]
        my_y = external_hinges_y["m1"].iloc[index]
        idx_x = external_hinges_x["index"].iloc[index]
        idx_y = external_hinges_y["index"].iloc[index]
        bay_n_x = external_hinges_x["Bay"].iloc[index]
        bay_n_y = external_hinges_y["Bay"].iloc[index]

        if my_x >= my_y:
            hinge_models_y.iloc[idx_y] = external_hinges_x.drop(columns=["index"]).iloc[index]
            # Modify corresponding Bay number
            hinge_models_y.at[idx_y, "Bay"] = bay_n_y

        else:
            hinge_models_x.iloc[idx_x] = external_hinges_y.drop(columns=["index"]).iloc[index]
            hinge_models_x.at[idx_x, "Bay"] = bay_n_x

    return hinge_models_x, hinge_models_y


directory = Path.cwd().parents[0]
case = "Case12a"
impClass = "III"
outputPath = directory / f".applications/LOSS Validation Manuscript/space/EC8/{case}"
flag3d = True

ipbsd = Master(directory, flag3d=flag3d)
input_file = outputPath / "ipbsd_input.csv"
# hazard_name = "Hazard-LAquila-Soil-C.pkl"
hazard_name = "hazard_ancona.pickle"
hazard_file = outputPath.parents[1] / hazard_name

# Hazard
with open(hazard_file.parents[0] / f'coef_{hazard_name}', 'rb') as file:
    coefs = pickle.load(file)

ipbsd.read_input(input_file, hazard_file, output_path=outputPath)
hazard = ipbsd.original_hazard

# Cross-section files
solution_x = pd.read_csv(outputPath / "solution_cache_space_x.csv", index_col=0).iloc[0]
solution_y = pd.read_csv(outputPath / "solution_cache_space_y.csv", index_col=0).iloc[0]
solution_gr = pd.read_csv(outputPath / "solution_cache_space_gr.csv", index_col=0).iloc[0]

solution = {"x_seismic": solution_x, "y_seismic": solution_y, "gravity": solution_gr}

# Input information
TR = 475
beta_al = .3
fstiff = .5
ductClass = "DCM"

# Global inputs
i_d = ipbsd.data.i_d
q_floor = i_d['bldg_ch'][0]
q_roof = i_d['bldg_ch'][1]
spans_x = np.array([])
spans_y = np.array([])
for key in i_d["spans_X"]:
    spans_x = np.append(spans_x, i_d["spans_X"][key])
for key in i_d["spans_Y"]:
    spans_y = np.append(spans_y, i_d["spans_Y"][key])
A_floor = sum(spans_x) * sum(spans_y)
heights = np.array([])
for key in i_d["h_storeys"]:
    heights = np.append(heights, i_d["h_storeys"][key])
nst = len(heights)
n_bays_x = len(spans_x)
n_bays_y = len(spans_y)
masses = np.zeros(nst)
for storey in range(nst):
    if storey == nst - 1:
        masses[storey] = q_roof * A_floor / 9.81
    else:
        masses[storey] = q_floor * A_floor / 9.81

fy = 415.
elastic_modulus_steel = 200000.
eps_y = fy / elastic_modulus_steel
fc = 25.
n_seismic = 2
Ec = 3320 * np.sqrt(fc) + 6900

# Deriving Fb distribution based on assumed T1 (not really being used here)
Ct = 0.075
T1 = round(Ct * sum(heights) ** (3 / 4), 1)
soil_class = 'C'
type_spectra = 1
damping = 0.05
S, Tb, Tc, Td, eta = spectra_par(soil_class, type_spectra, damping)

# Create the 3D model and perform modal analysis to identify the actual period
hinge = {"x_seismic": None, "y_seismic": None, "gravity": None}
model_periods, modalShape, gamma, mstar = ipbsd.ma_analysis(solution, hinge, None, fstiff, direction=0)

# Get the ELFs for each direction
Fi = np.zeros((2, nst))
hinge_models = {"x_seismic": None, "y_seismic": None, "gravity": None}
demands_gravity = {}

for i in range(Fi.shape[0]):
    T1 = model_periods[i]
    T1_tag = 'SA(%.2f)' % 0.3 if round(T1, 1) == 0.3 else 'SA(%.1f)' % T1

    # _, SaT1, _, _ = _hazard(coefs[T1_tag], TR, beta_al)
    # _, PGA, _, _ = _hazard(coefs['PGA'], TR, beta_al)

    # PGA
    Hs = hazard[2][0]
    sa_range = hazard[1][0]
    interpolation = interp1d(Hs, sa_range)
    PGA = interpolation(1 / TR)

    # SaT1
    idx = int(round(T1*10, 0))
    Hs = hazard[2][idx]
    sa_range = hazard[1][idx]
    interpolation = interp1d(Hs, sa_range)
    SaT1 = interpolation(1 / TR)

    print(PGA, SaT1)
    print(f"[PERIOD] {T1}s")

    # EC8 table 5.1, 5.2.2.2
    # assuming DCM or DCH and multi-storey multi-bay frame
    q0 = 3 * 1.3 if ductClass == 'DCM' else 4.5 * 1.3
    # for frame and frame equivalent dual systems
    kw = 1
    q = max(1.5, q0 * kw)
    yI = 0.8 if impClass == 'I' else 1.0 if impClass == 'II' else 1.2 if impClass == 'III' else 1.4
    T, Sa = get_ECelastic_spectra(PGA, soil_class)
    SaFactor = float(Sa[getIndex(T1, T)] / SaT1)
    Sa = Sa / SaFactor / q if T1 >= Tb else (5 / 3 + T1 / Tb * (2.5 / q - 2 / 3)) / (
            1 + T1 / Tb * (2.5 - 1)) * Sa / SaFactor
    Lam = 0.85 if (T1 <= 2 * Tc) and (nst > 2) else 1
    SaT1 = Sa[getIndex(T1, T)] * yI
    print(f"[SaT1] {SaT1:.2}")

    m = masses / n_seismic
    Fb = SaT1 * 9.81 * sum(m) * Lam
    z = np.cumsum(heights)
    Fi[i, :] = np.array([float(Fb * m[i] * z[i] / sum(map(lambda x, y: x * y, z, m))) for i in range(nst)])

    # Getting the demands by applying the forces along each direction sequentially
    analysis_type = 3
    demands = ipbsd.run_analysis(analysis_type, solution, Fi[i], grav_loads=None, fstiff=fstiff, hinge=hinge,
                                 direction=i)

    # Details the frame of seismic direction only
    gr_id = "x" if i == 0 else "y"
    print(f"[DESIGN] {gr_id} direction")
    demands_gravity[gr_id] = demands["gravity"]
    seismic_demands = demands["x_seismic"] if i == 0 else demands["y_seismic"]
    seismic_solution = solution["x_seismic"] if i == 0 else solution["y_seismic"]
    modes = modalShape[:, 0]

    dy = None
    details, hinges, mu_c, mu_f, warnMax, warnMin, warnings = \
        ipbsd.design_elements(seismic_demands, seismic_solution, modes, dy, cover=0.03,
                              direction=i, est_ductilities=False)

    warnings_min = sum(warnings["MIN"]["Columns"].values())
    warnings_max = sum(warnings["MAX"]["Columns"].values())
    n_elements = len(warnings["MIN"]["Columns"])

    print(f"[WARNINGS] MIN: {warnings_min / n_elements * 100}%")
    print(f"[WARNINGS] MAX: {warnings_max / n_elements * 100}%")

    if i == 0:
        hinge_models["x_seismic"] = hinges
    else:
        hinge_models["y_seismic"] = hinges

# Design the central elements (envelope of both directions)
hinge_gravity, warn_gravity = ipbsd.design_elements(demands_gravity, solution["gravity"], None, None,
                                                    cover=0.03, direction=0, gravity=True,
                                                    est_ductilities=False)

warnings_min = sum(warn_gravity["warnings"]["MIN"]["Columns"].values())
warnings_max = sum(warn_gravity["warnings"]["MAX"]["Columns"].values())
n_elements = len(warn_gravity["warnings"]["MIN"]["Columns"])
print(f"[WARNINGS] MIN: {warnings_min / n_elements * 100}%")
print(f"[WARNINGS] MAX: {warnings_max / n_elements * 100}%")

hinge_x, hinge_y = get_critical_designs(hinge_models["x_seismic"], hinge_models["y_seismic"])
hinge_models["x_seismic"] = hinge_x
hinge_models["y_seismic"] = hinge_y
hinge_models["gravity"] = hinge_gravity

"""
Inputs necessary for RCMRF
hinge_models.csv
materials.csv
action.csv
"""

for i in hinge_models.keys():
    export_results(outputPath / "hinge_models", hinge_models, "pickle")
