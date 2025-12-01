import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from b1500a.config import (
    UNITS,
    IVSWEEP_VOLT_COL,
    IVSWEEP_CURR_COL,
    GATESWEEP_VOLT_COL,
    GATESWEEP_CURR_COL,
)
from b1500a.utils import extract_metadata


def _load_csv_rows(fpath):
    """Read a CSV-like text file into a list of stripped row lists."""

    rows = []
    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            rows.append([item.strip() for item in line.rstrip("\n\r").split(",")])
    return rows


def _build_meas_dataframe(rows):
    """Convert raw CSV rows into a measurement DataFrame."""

    data_name_idx = None
    for idx, row in enumerate(rows):
        if row and row[0] == "DataName":
            data_name_idx = idx
            break

    if data_name_idx is None or data_name_idx == len(rows) - 1:
        return pd.DataFrame()

    data_col_names = np.array(rows[data_name_idx])
    meas_rows = rows[data_name_idx + 1 :]
    meas_df = pd.DataFrame(meas_rows, columns=data_col_names)
    if "DataName" in meas_df.columns:
        meas_df = meas_df.drop(columns=["DataName"])
    
    # Convert all numeric columns to float for downstream calculations
    meas_df = meas_df.apply(pd.to_numeric, errors="coerce")

    return meas_df


def _extract_test_parameters(rows):
    """Extract TestParameter rows into a dictionary."""
    params = {}
    for row in rows:
        if row and row[0] == "TestParameter" and len(row) > 1:
            key = row[1]
            values = row[2:]
            if len(values) == 1:
                params[key] = values[0]
            else:
                params[key] = values
    return params


class DataFile:
    def __init__(self, fpath, smus=3):
        """
        Base class for parsing Agilent B1500A data files

        Parameters
        ----------
        fpath: path to file of interest
        smus: number of source/measurement units equipped on the B1500A (default is 3)
        """

        self.fpath = fpath
        self.fname = os.path.basename(fpath)
        self.smus = smus
        self.metadata = extract_metadata(os.path.basename(fpath))
        self.volts = []
        self.current = []

        rows = _load_csv_rows(self.fpath)
        self.meas_data = _build_meas_dataframe(rows)
        self.params = _extract_test_parameters(rows)

    def save_csv(self, fpath):
        """Save raw measurement data to CSV"""
        self.meas_data.to_csv(fpath, index=False)


class MultiDataFile(DataFile):
    """DataFile subclass for CSVs containing multiple concatenated data blocks.

    This class keeps a list of individual measurement blocks in `meas_blocks`.
    Each block is a DataFrame corresponding to one "DataName"/"DataValue" pair.
    """

    def __init__(self, fpath, smus=3):
        # store basic info
        self.fpath = fpath
        self.fname = os.path.basename(fpath)
        self.smus = smus
        self.metadata = extract_metadata(os.path.basename(fpath))
        self.volts = []
        self.current = []

        all_rows = _load_csv_rows(self.fpath)

        self.meas_blocks = []
        self.block_titles = []
        self.block_params = []

        setup_indices = [idx for idx, row in enumerate(all_rows) if row and row[0] == "SetupTitle"]
        if not setup_indices:
            meas_data = _build_meas_dataframe(all_rows)
            if not meas_data.empty:
                self.meas_blocks.append(meas_data)
            self.meas_data = meas_data
            
            self.params = _extract_test_parameters(all_rows)
            self.block_params.append(self.params)
            return

        for idx, start in enumerate(setup_indices):
            end = setup_indices[idx + 1] if idx + 1 < len(setup_indices) else len(all_rows)
            block_rows = all_rows[start:end]

            setup_row = all_rows[start]
            setup_title = setup_row[1] if len(setup_row) > 1 else ""

            meas_data = _build_meas_dataframe(block_rows)
            if meas_data.empty:
                continue

            meas_data = meas_data.copy()
            # Each row keeps a "SetupTitle" column indicating its source block.
            meas_data["SetupTitle"] = setup_title

            self.meas_blocks.append(meas_data)
            self.block_titles.append(setup_title)
            self.block_params.append(_extract_test_parameters(block_rows))

        # For compatibility with DataFile API, expose all blocks stacked together
        if self.meas_blocks:
            self.meas_data = pd.concat(self.meas_blocks, ignore_index=True)
            self.params = self.block_params[0]
        else:
            self.meas_data = pd.DataFrame()
            self.params = {}

class IVSweep(DataFile):
    """
    Class that contains data for IV sweep tests (inherits from DataFile object)
    """

    def __init__(self, fpath, smus=3, volt=IVSWEEP_VOLT_COL, curr=IVSWEEP_CURR_COL):
        super().__init__(fpath, smus)
        self.volts = [float(i) for i in self.meas_data[volt]]
        self.current = [float(i) for i in self.meas_data[curr]]
        self.volt_units = ""
        self.current_units = ""

        self.fit = np.polyfit(self.volts, self.current, 1)
        self.resistance = 1/self.fit[0]

        self.v_fit = np.arange(self.volts[0], self.volts[-1], (self.volts[-1]-self.volts[0])/len(self.volts))
        self.i_fit = [(i*self.fit[0])+self.fit[1] for i in self.v_fit]

    def plot(self, fit=False, save=False, show=False, color="blue"):
        """
        Plots the data

        Parameters
        ----------
        fit: whether or not to display the fitted curve (boolean)
        save: whether or not to save the image (False if no save, provide a file path if yes save)
        show: whether or not to show the image (boolean)
        color: color of plotted line

        Returns
        ----------
        None (plots/saves/shows data)
        """

        plt.plot(self.volts, self.current, color=color, label=self.metadata["DeviceName"])
        if fit:
            plt.plot(self.v_fit, self.i_fit, linestyle="--", color="black")

        plt.legend()

        if save:
            plt.savefig(save)

        if show:
            plt.show()

    def change_units(self, parameter, unit):
        """
        Updates units to provided scale

        Parameters
        ----------
        parameter: which data parameter to change (currently only voltage ('V') or current ('I'))
        unit: which unit to change to (see config.UNITS for options)

        Returns
        ----------
        None (updates corresponding parameter)
        """

        if parameter.upper() == "V":
            if self.volt_units != "":
                self.volts = [i*UNITS[unit] for i in self.volts]
                self.v_fit = [i*UNITS[unit] for i in self.v_fit]
            self.volts = [i/UNITS[unit] for i in self.volts]
            self.v_fit = [i/UNITS[unit] for i in self.v_fit]
            self.volt_units = unit
        elif parameter.upper() == "I":
            if self.current_units != "":
                self.current = [i*UNITS[unit] for i in self.current]
                self.i_fit = [i*UNITS[unit] for i in self.i_fit]
            self.current = [i/UNITS[unit] for i in self.current]
            self.i_fit = [i/UNITS[unit] for i in self.i_fit]
            self.current_units = unit
        else:
            print(f"Bad value for 'parameter' ({parameter}), should be 'V' for volts or 'I' for current")

    def save_csv(self, fpath):
        """
        Method for saving a simpler .csv file

        Parameters
        ----------
        fpath: file path to save to
        """
        pd.DataFrame(data={f"Volts ({self.volt_units}V)": self.volts, f"Current ({self.current_units}A)": self.current}).to_csv(fpath, index=False)


class GateSweep(DataFile):
    """
    Class that contains data for gate sweep tests (inherits from DataFile object)
    """

    def __init__(self, fpath, smus=3, volt=GATESWEEP_VOLT_COL, curr=GATESWEEP_CURR_COL):
        super().__init__(fpath, smus)
        self.volts = [float(i) for i in self.meas_data[volt]]
        self.current = [float(i) for i in self.meas_data[curr]]
        self.volt_units = ""
        self.current_units = ""

        self.fit = np.polyfit(self.volts, self.current, 2)
        self.dirac = -self.fit[1]/(2*self.fit[0])

        self.v_fit = np.arange(self.volts[0], self.volts[-1], (self.volts[-1]-self.volts[0])/len(self.volts))
        self.i_fit = [(i*i*self.fit[0])+(i*self.fit[1])+self.fit[2] for i in self.v_fit]

    def plot(self, fit=False, save=False, show=False, color="blue"):
        """
        Plots the data

        Parameters
        ----------
        fit: whether or not to display the fitted curve (boolean)
        save: whether or not to save the image (False if no save, provide a file path if yes save)
        show: whether or not to show the image (boolean)
        color: color of plotted line

        Returns
        ----------
        None (plots/saves/shows data)
        """

        plt.plot(self.volts, self.current, color=color, label=self.metadata["DeviceName"])

        if fit:
            plt.plot(self.v_fit, self.i_fit, linestyle="--", color="black")

        plt.legend()

        if save:
            plt.savefig(save)
        if show:
            plt.show()

    def change_units(self, parameter, unit):
        """
        Updates units to provided scale

        Parameters
        ----------
        parameter: which data parameter to change (currently only voltage ('V') or current ('I'))
        unit: which unit to change to (see config.UNITS for options)

        Returns
        ----------
        None (updates corresponding parameter)
        """

        if parameter.upper() == "V":
            if self.volt_units != "":
                self.volts = [i*UNITS[unit] for i in self.volts]
                self.v_fit = [i*UNITS[unit] for i in self.v_fit]
            self.volts = [i/UNITS[unit] for i in self.volts]
            self.v_fit = [i/UNITS[unit] for i in self.v_fit]
            self.volt_units = unit
        elif parameter.upper() == "I":
            if self.current_units != "":
                self.current = [i*UNITS[unit] for i in self.current]
                self.i_fit = [i*UNITS[unit] for i in self.i_fit]
            self.current = [i/UNITS[unit] for i in self.current]
            self.i_fit = [i/UNITS[unit] for i in self.i_fit]
            self.current_units = unit
        else:
            print(f"Bad value for 'parameter' ({parameter}), should be 'V' for volts or 'I' for current")

    def save_csv(self, fpath):
        """
        Method for saving a simpler .csv file

        Parameters
        ----------
        fpath: file path to save to
        """
        pd.DataFrame(data={f"Volts ({self.volt_units}V)": self.volts, f"Current ({self.current_units}A)": self.current}).to_csv(fpath, index=False)

