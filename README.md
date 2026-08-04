# Home Assistant tools reporting tools

Small quality of life tools for Home Assistant reporting

I have been writing some scripts on retrieving information from Home Assistant. My HA environment has been growing
considerably in the past few years, and I discovered that applying proper administration, such as labels, areas, and
categories, is always an afterthought. And, don't even mention physically labeling your sensors, switches, and other
hardware.

When you also have a mix of equipment, using Matter, Zigbee, and RF, you get to a point that it gets complex. Without
proper administration t's challenging to find the relation between an HA error, your HA environment, and the physical
reality.

Untangling, auditing and administrating everything needs insight first, and for me, the HA web interface is not always
my first choice; I am more of an Excel guy myself.

Anyway, I had a couple of issues I wanted to audit and resolve. The below scripts are the result of that.

**1. Pulling and comparing Home Assistant and InfluxDB entities.**  
I'm using an InfluxDB database to collect a crazy amount of data from entities. I wasn't sure which entities were
actually being reported to InfluxDB compared to the entities that live in the HA environment. On paper it looked fine;
you can see in the configuration what data is being sent to InfluxDB. But does it actually arrive there, and is it
stored properly?

That's why I created 2 Python scripts, **HA_entities_reporting.py** and **HA_influx_reporting.py**, that pull entity
data from InfluxDB and Home Assistant in a way that makes it possible to compare which entities are available on Home
Assistant and which entities are reported in InfluxDB. This enables you to find discrepancies between those two and if
it's complying with what you expected from your configuration.

**2. Obtaining Matter and Thread information.**  
I have a growing number of Matter over Thread devices. There's a lot of information available, using the "Open Home
Foundation Matter Server", but finding the relation between the HA devices and the Matter/Thread environment is not
always obvious.

That's the reason I've created a Python script, **HA_matter_reporting.py**, that attempts to report all the Matter
devices and show as much information as possible about each device, including Thread information.

**3. Audit your labeling.**  
I started labeling all my devices to make it easier to select groups of devices. When I say labeling, I mean labels,
categories, areas, and floors. Once you've done that, creating scripts and automations will be much easier, or select
subsets of devices and entities. The **HA_labels_reporting.py** script can help you with that. It reports on entities
and devices, using custom rules. It's easier to find devices that are missing labels or have wrong labels.

**There are more ways leading to Rome.**  
I am aware there are probably many other ways to retrieve the information, but I've taken this approach. In case other
community members can use these scripts to their advantage, I decided to share them in a Github repository. You are
welcome to use them; they are there to share!

**Next?**  
Not much, I'm afraid, but I will be sharing a document on how to use the CSV output files and pull them into Excel in
the best way. This is especially convenient in the case of comparing InfluxDB with Home Assistant. Excel enables you to
dynamically go through the data and see discrepancies.

https://github.com/RudiKlein/home-assistant-reporting-tools

## Important Note

* These scripts are **not** Home Assistant add-ons. They are standalone Python scripts that run on your local machine or server and connect to Home Assistant and/or InfluxDB via APIs.
* These scripts are not affiliated with or endorsed by Home Assistant and/or InfluxDB. They are independent tools created by someone who thinks he's a developer.
* They are designed to be run periodically (e.g., via cron), or manually, to generate a snapshot of your Home Assistant for analysis and reporting.
* They are intended for users who are comfortable with Python and command-line tools, and who have a working knowledge of Home Assistant's device and entity model.
* They are provided as-is, with no warranty or support. Use at your own risk. Live on the edge.
* However, if you find them useful, please consider contributing back to the project by submitting issues, pull requests, or comforting compliments.
* I want to extend my gratitude to my friend Claude for its support, inspiration, its context drift, hallucination loops, erratic behavior, and false outputs.
```
```
