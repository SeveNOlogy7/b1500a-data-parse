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

        self.column_names = ["Category", "Measurement"] + [f"SMU{i}" for i in range(1, self.smus+1)]
        self.all_data = pd.read_csv(self.fpath, names=self.column_names)
        
        self.data_col_names = np.array(self.all_data[self.all_data["Category"] == "DataName"].iloc[0].dropna())
        self.meas_data = self.all_data[self.all_data["Category"] == "DataValue"].dropna(axis=1).reset_index(drop=True)
        self.meas_data = self.meas_data.rename(
            columns={i: j.strip() for i, j in zip(self.meas_data.columns, self.data_col_names)}
        )

    def save_csv(self, fpath):
        """Save raw measurement data to CSV, excluding the DataName column if present."""

        df = self.meas_data.copy()
        if "DataName" in df.columns:
            df = df.drop(columns=["DataName"])
        df.to_csv(fpath, index=False)


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

        # read full CSV once
        column_names = ["Category", "Measurement"] + [f"SMU{i}" for i in range(1, smus + 1)]
        all_data = pd.read_csv(self.fpath, names=column_names)

        # find indices where a new setup/file starts
        setup_indices = all_data.index[all_data["Category"] == "SetupTitle"].tolist()
        if not setup_indices:
            # fallback: treat whole file as one DataFile
            tmp = DataFile(fpath, smus)
            self.all_data = tmp.all_data
            self.meas_blocks = [tmp.meas_data]
            self.meas_data = tmp.meas_data
            return

        self.meas_blocks = []
        self.block_titles = []

        for idx, start in enumerate(setup_indices):
            end = setup_indices[idx + 1] if idx + 1 < len(setup_indices) else len(all_data)
            sub_df = all_data.iloc[start:end]

            # get SetupTitle (Measurement field on SetupTitle row)
            setup_row = all_data.iloc[start]
            setup_title = str(setup_row["Measurement"]) if "Measurement" in setup_row else ""

            # write this slice to a temporary in-memory CSV via DataFrame
            # then reuse DataFile logic by constructing a DataFile-like object
            # We mimic DataFile processing here to avoid extra IO.
            data_name_rows = sub_df[sub_df["Category"] == "DataName"]
            if data_name_rows.empty:
                continue

            data_col_names = np.array(data_name_rows.iloc[0].dropna())
            meas_data = sub_df[sub_df["Category"] == "DataValue"].dropna(axis=1).reset_index(drop=True)
            meas_data = meas_data.rename(
                columns={i: j.strip() for i, j in zip(meas_data.columns, data_col_names)}
            )
            # add a column to identify which SetupTitle this block came from
            meas_data = meas_data.copy()
            meas_data["SetupTitle"] = setup_title

            self.meas_blocks.append(meas_data)
            self.block_titles.append(setup_title)

        # assemble all_data for this MultiDataFile (concatenate for reference)
        self.all_data = all_data

        # For compatibility with DataFile API, expose the first block as meas_data
        self.meas_data = self.meas_blocks[0] if self.meas_blocks else pd.DataFrame()

    def save_csv(self, fpath):
        """Save all measurement blocks to one CSV, stacked vertically.

        The DataName column is excluded if present in any block.
        Each row keeps a "SetupTitle" column indicating its source block.
        """

        if not self.meas_blocks:
            pd.DataFrame().to_csv(fpath, index=False)
            return

        cleaned_blocks = []
        for df in self.meas_blocks:
            block = df.copy()
            if "DataName" in block.columns:
                block = block.drop(columns=["DataName"])
            cleaned_blocks.append(block)

        full_df = pd.concat(cleaned_blocks, ignore_index=True)
        full_df.to_csv(fpath, index=False)

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

