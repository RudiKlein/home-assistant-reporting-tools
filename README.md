# Home Assistant tools reporting tools

Small quality of life improvement reporting tools for Home Assistant

## Important Note

* These scripts are **not** Home Assistant add-ons. They are standalone Python scripts that run on your local machine or server and connect to Home Assistant and/or InfluxDB via APIs.
* These scripts are not affiliated with or endorsed by Home Assistant or InfluxDB. They are independent tools created by someone who thinks he's a developer.
* They are designed to be run periodically (e.g., via cron), or manually, to generate a snapshot of your Home Assistant and InfluxDB data for analysis and reporting.
* They are intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of Home Assistant's device and entity model.
* They are provided as-is, with no warranty or support. Use at your own risk. Live on the edge.
* However, if you find them useful, please consider contributing back to the project by submitting issues, pull requests, or comforting compliments.
* I want to extend my gratitude to my friend Claude for its support, inspiration, its context drift, hallucination loops, erratic behavior, and false outputs.