## Importing Home Assistant entities reporting CSV data into Excel

In this folder you will find 2 files that represent the data collected from the Matter reporting tool. The first file is a CSV that contains the raw data, while the second file is an Excel spreadsheet that contains a formatted version of the data.

The CSV file is named "influx_data.csv" and includes all the unprocessed data collected from the Influx reporting tool. This file is useful for those who want to perform their own analysis or processing of the data.

The Excel file is named "HA_entities_comparison.xlsx" and provides a more user-friendly view of the data. It includes various formatting features such as headers, slicers (filters), and other formatting to make it easier to read and interpret the information.

Note: the HA_entities_comparison.xlsx is identical to the HA_entities_comparison.xlsx file in the HA_entities_reporting folder, but it is included here for convenience.

The Excel file used both influx_ha_entities.csv and the home_assistant_entities.csv, produced by the Home Assistant entities reporting tool (see folder HA_influx_reporting in this repo), to create a comparison of the two datasets. 

The CSV data was imported into the Excel file, by using Excel's built-in data import functionality. In order to insert your own data into the Excel file, you can follow these steps:

1. Open the "HA_entities_comparison.xlsx" file in Microsoft Excel.
2. Go to the "Data" tab in the Excel ribbon.
3. Click on "Get Data" and select "Data Source Settings" to configure the data source.
4. In the "Data Source Settings" window, click on "Change Source" and select your "influx_ha_entities.csv" and "home_assistant_entities.csv" (or the names you have given to the output file) file as the new data sources.
5. Click "OK" to apply the changes and refresh the data in the Excel file.
6. Save the Excel file to retain the new data source configuration.
7. Click on the "Refresh All" button in the "Data" tab to update the data in the Excel file with the new information from your CSV file.

From now on, any changes made to the CSV file will be reflected in the Excel file when you refresh the data. This allows you to keep your Excel file up-to-date with the latest data collected from the Matter reporting tool.

Use the slicers and filters in the Excel file to analyze and visualize the data as needed.
