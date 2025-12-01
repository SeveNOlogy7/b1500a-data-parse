import numpy as np

def avg_lin_fit(data):
    """
    Calculates and returns average linear fit for a set of data

    Parameters
    ----------
    data: list of data sets (each list element should be all data from a test in format [x,y])
            each data set should have the same x-axis and be the same length
    """

    avg_y = []
    for i in range(len(data[0][1])):
        avg_y.append(np.mean([data[j][1][i] for j in range(len(data))]))

    fit_params = np.polyfit(data[0][0], avg_y, 1)

    x_fit = np.arange(data[0][0][0], data[0][0][-1], (data[0][0][-1]-data[0][0][0])/len(data[0][0]))
    y_fit = [(i*fit_params[0])+fit_params[1] for i in x_fit]

    return x_fit, y_fit

def avg_parab_fit(data):
    """
    Calculates and returns average parabolic fit for a set of data

    Parameters
    ----------
    data: list of data sets (each list element should be all data from a test in format [x,y])
            each data set should have the same x-axis and be the same length
    """

    avg_y = []
    for i in range(len(data[0][1])):
        avg_y.append(np.mean([data[j][1][i] for j in range(len(data))]))


    fit_params = np.polyfit(data[0][0], avg_y, 2)
 
    x_fit = np.arange(data[0][0][0], data[0][0][-1], (data[0][0][-1]-data[0][0][0])/len(data[0][0]))
    y_fit = [(i*i*fit_params[0])+(i*fit_params[1])+fit_params[2] for i in x_fit]

    return x_fit, y_fit
