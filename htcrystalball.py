#!/usr/bin/env python3

"""Gives users a preview on how and where they can execute their HTcondor compatible scripts."""
import os
import argparse
import json
import re
import math
from rich.console import Console
from rich.table import Table
import logging

# External (root level) logging level
logging.basicConfig(level=logging.ERROR)

# Internal logging level
logger = logging.getLogger('scrape_energy')
logger.setLevel(level=logging.DEBUG)

SLOTS_CONFIGURATION = "config/slots.json"


def validate_storage_size(arg_value: str) -> str:
    """
    Defines and checks valid storage inputs.

    Args:
        arg_value: The given storage input string

    Returns:
        The valid storage string or raises an exception if it doesn't match the regex.
    """

    pat = re.compile(r"^[0-9]+([kKmMgGtTpP]i?[bB]?)$")

    if not pat.match(arg_value):
        logging.error("Invalid storage value given: '"+arg_value+"'\n")
        raise argparse.ArgumentTypeError
    return arg_value


def validate_duration(arg_value: str) -> str:
    """
    Defines and checks valid time inputs.

    Args:
        arg_value: The given duration input string

    Returns:
        The valid duration string or raises an exception if it doesn't match the regex.
    """
    pat = re.compile(r"^([0-9]+([dDhHmMsS]?))?$")

    if not pat.match(arg_value):
        logging.error("Invalid time value given: '"+arg_value+"'\n")
        raise argparse.ArgumentTypeError
    return arg_value


def split_number_unit(user_input: str) -> [float, str]:
    """
    Splits the user input for storage sizes into number and storage unit.
    If no value or unit is given, the unit is set to GiB.

    Args:
        user_input: The given number string

    Returns:
        The amount and unit string separated in a list.
    """
    if not user_input:
        return [0.0, "GiB"]

    splitted = re.split(r'(\d*\.?\d+)', user_input.replace(' ', ''))

    amount = float(splitted[1])
    if splitted[2] == "":
        unit = "GiB"
        logging.info("No storage unit given, using GiB as default.")
    else:
        unit = splitted[2]

    return [amount, unit]


def split_duration_unit(user_input: str) -> [float, str]:
    """
    Splits the user input for time into number and time unit.
    If no value or unit is given, the unit is set to minutes.

    Args:
        user_input: The given duration string

    Returns:
        The duration and unit string separated in a list.
    """
    if user_input == "" or user_input is None:
        return [0.0, "min"]

    splitted = re.split(r'(\d*\.?\d+)', user_input.replace(' ', ''))

    amount = float(splitted[1])
    if splitted[2] == "":
        unit = "min"
        logging.info("No duration unit given, using MIN as default.")
    else:
        unit = splitted[2]

    return [amount, unit]


def calc_to_bin(number: float, unit: str) -> float:
    """
    Converts a storage value to GiB and accounts for base2 and base10 units.

    Args:
        number: The storage size number
        unit: The storage unit string

    Returns:
        The storage size number converted to GiB
    """
    unit_indicator = unit.lower()
    if unit_indicator in ("kb", "k", "kib"):
        return number / (10 ** 6)
    if unit_indicator in ("mb", "m", "mib"):
        return number / (10 ** 3)
    if unit_indicator in ("tb", "t", "tib"):
        return number * (10 ** 3)
    if unit_indicator in ("pb", "p", "pib"):
        return number * (10 ** 6)
    return number


def calc_to_min(number: float, unit: str) -> float:
    """
    Converts a time value to minutes, according to the given unit.

    Args:
        number: The duration number
        unit: The duration unit string

    Returns:
        The duration number converted to minutes
    """
    unit_indicator = unit.lower()
    if unit_indicator in ("d", "dd"):
        return number * 24 * 60
    if unit_indicator in ("h", "hh"):
        return number * 60
    if unit_indicator in ("s", "ss"):
        return number / 60
    return number


def define_environment():
    """
    Defines the command line arguments and required formats.

    Returns:

    """
    parser = argparse.ArgumentParser(
        description="To get a preview for any job you are trying to execute using "
                    "HTCondor, please pass at least the number of CPUs and "
                    "the amount of RAM "
                    "(including units eg. 100MB, 90M, 10GB, 15G) to this script "
                    "according to the usage example shown above. For JOB Duration please "
                    "use d, h, m or s", prog='htcrystalball.py',
        usage='%(prog)s -c CPU -r RAM [-g GPU] [-d DISK] [-j JOBS] [-d DURATION] [-v]',
        epilog="PLEASE NOTE: HTCondor always uses binary storage "
               "sizes, so inputs will automatically be treated that way.")
    parser.add_argument("-v", "--verbose", help="Print extended log to stdout",
                        action='store_true')
    parser.add_argument("-c", "--cpu", help="Set number of requested CPU Cores",
                        type=int, required=True)
    parser.add_argument("-g", "--gpu", help="Set number of requested GPU Units",
                        type=int)
    parser.add_argument("-j", "--jobs", help="Set number of jobs to be executed",
                        type=int)
    parser.add_argument("-t", "--time", help="Set the duration for one job "
                                             "to be executed", type=validate_duration)
    parser.add_argument("-d", "--disk", help="Set amount of requested disk "
                                             "storage", type=validate_storage_size)
    parser.add_argument("-r", "--ram", help="Set amount of requested memory "
                                            "storage", type=validate_storage_size, required=True)
    parser.add_argument("-m", "--maxnodes", help="Set maximum of nodes to "
                                                 "run jobs on", type=int)

    cmd_parser = parser.parse_args()
    return cmd_parser


def define_slots() -> dict:
    """
    Loads the slot configuration.

    Returns:

    """
    with open(SLOTS_CONFIGURATION) as config_file:
        data = json.load(config_file)
    return data["slots"]


def filter_slots(slots: dict, slot_type: str) -> list:
    """
    Filters the slots stored in a dictionary according to their type.

    Args:
        slots: Dictionary of slots
        slot_type: requested Slot Type for filtering

    Returns:
        A filtered dictionary of slots
    """
    res = []
    for node in slots:
        for slot in node["slot_size"]:
            if slot["SlotType"] == slot_type:
                slot["UtsnameNodename"] = node["UtsnameNodename"]
                res.append(slot)
    return res


#  print out what the user gave as input
def pretty_print_input(num_cpu: int, amount_ram: float, amount_disk: float, num_gpu: int,
                       num_jobs: int, num_duration: float, max_nodes: int):
    """
    Prints out the already converted user input to the console using rich tables.

    Args:
        num_cpu: The requested number CPU cores
        amount_ram: The requested amount of RAM
        amount_disk: The requested amount of disk space
        num_gpu: The requested number of GPU units
        num_jobs: The user-defined amount of similar jobs
        num_duration: The user-defined estimated duration per job
        max_nodes: The user-defined maximum number of simultaneous occupied nodes

    Returns:

    """
    console = Console()

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Parameter", style="dim")
    table.add_column("Input Value", justify="right")
    table.add_row(
        "CPUS",
        str(num_cpu)
    )
    table.add_row(
        "RAM",
        "{0:.2f}".format(amount_ram) + " GiB"
    )
    table.add_row(
        "STORAGE",
        "{0:.2f}".format(amount_disk) + " GiB"
    )
    table.add_row(
        "GPUS",
        str(num_gpu)
    )
    table.add_row(
        "JOBS",
        str(num_jobs)
    )
    table.add_row(
        "JOB DURATION",
        "{0:.2f}".format(num_duration) + " min"
    )
    table.add_row(
        "MAXIMUM NODES",
        str(max_nodes)
    )
    console.print("---------------------- INPUT ----------------------")
    console.print(table)


def pretty_print_slots(result: dict):
    """
    Prints out the slots to the console using rich tables.

    Args:
        result: A dictionary of slot configurations.

    Returns:

    """
    console = Console()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Node", style="dim", width=12)
    table.add_column("Slot Type")
    table.add_column("Total Slots", justify="right")
    table.add_column("Cores", justify="right")
    table.add_column("GPUs", justify="right")
    table.add_column("RAM", justify="right")
    table.add_column("DISK", justify="right")

    for slot in result['slots']:
        if slot['type'] == "static":
            table.add_row("[dark_blue]" + slot['node'] + "[/dark_blue]",
                          "[dark_blue]" + slot['type'] + "[/dark_blue]",
                          "[dark_blue]" + str(slot['total_slots']) + "[/dark_blue]",
                          "[dark_blue]" + str(slot['cores']) + "[/dark_blue]",
                          "[dark_blue]------[/dark_blue]",
                          "[dark_blue]" + str(slot['ram']) + " GiB[/dark_blue]",
                          "[dark_blue]" + str(slot['disk']) + " GiB[/dark_blue]")
        elif slot['type'] == "gpu":
            table.add_row("[purple4]" + slot['node'] + "[/purple4]",
                          "[purple4]" + slot['type'] + "[/purple4]",
                          "[purple4]" + str(slot['total_slots']) + "[/purple4]",
                          "[purple4]" + str(slot['cores']) + "[/purple4]",
                          "[purple4]" + str(slot['gpus']) + "[/purple4]",
                          "[purple4]" + str(slot['ram']) + " GiB[/purple4]",
                          "[purple4]" + str(slot['disk']) + " GiB[/purple4]")
        else:
            table.add_row("[dark_red]" + slot['node'] + "[/dark_red]",
                          "[dark_red]" + slot['type'] + "[/dark_red]",
                          "[dark_red]" + str(slot['total_slots']) + "[/dark_red]",
                          "[dark_red]" + str(slot['cores']) + "[/dark_red]",
                          "[dark_red]------[/dark_red]",
                          "[dark_red]" + str(slot['ram']) + " GiB[/dark_red]",
                          "[dark_red]" + str(slot['disk']) + " GiB[/dark_red]")

    console.print("---------------------- NODES ----------------------")
    console.print(table)


def pretty_print_result(result: dict, verbose: bool):
    """
    Prints out the preview result to the console using rich tables.

    Args:
        result: A dictionary of slot configurations including occupancy values for
        the requested job size.
        verbose: A value to extend the generated output.

    Returns:

    """
    console = Console()

    table = Table(show_header=True, header_style="bold cyan")
    if verbose:
        table.add_column("Node", style="dim", width=12)
    table.add_column("Slot Type")
    table.add_column("Job fits", justify="right")
    if verbose:
        table.add_column("Slot usage", justify="right")
        table.add_column("RAM usage", justify="center")
        table.add_column("GPU usage", justify="center")
    table.add_column("Amount of similar jobs", justify="right")
    table.add_column("Wall Time on IDLE", justify="right")

    for slot in result['preview']:
        if slot['fits'] == "YES":
            if verbose:
                table.add_row("[green]" + slot['name'] + "[/green]",
                              "[green]" + slot['type'] + "[/green]",
                              "[green]" + slot['fits'] + "[/green]",
                              "[green]" + slot['core_usage'] + " Cores[/green]",
                              "[green]" + slot['ram_usage'] + "[/green]",
                              "[green]" + slot['gpu_usage'] + "[/green]",
                              "[green]" + str(slot['sim_jobs']) + "[/green]",
                              "[green]" + str(slot['wall_time_on_idle']) + " min[/green]")
            else:
                table.add_row("[green]" + slot['type'] + "[/green]",
                              "[green]" + slot['fits'] + "[/green]",
                              "[green]" + str(slot['sim_jobs']) + "[/green]",
                              "[green]" + str(slot['wall_time_on_idle']) + " min[/green]")
        else:
            if verbose:
                table.add_row("[red]" + slot['name'] + "[/red]",
                              "[red]" + slot['type'] + "[/red]",
                              "[red]" + slot['fits'] + "[/red]",
                              "[red]" + slot['core_usage'] + " Cores[/red]",
                              "[red]" + slot['ram_usage'] + "[/red]",
                              "[red]" + slot['gpu_usage'] + "[/red]",
                              "[red]" + str(slot['sim_jobs']) + "[/red]",
                              "[red]" + str(slot['wall_time_on_idle']) + " min[/red]")
            else:
                table.add_row("[red]" + slot['type'] + "[/red]",
                              "[red]" + slot['fits'] + "[/red]",
                              "[red]" + str(slot['sim_jobs']) + "[/red]",
                              "[red]" + str(slot['wall_time_on_idle']) + " min[/red]")

    console.print("---------------------- PREVIEW ----------------------")
    console.print(table)


def check_slots(static: list, dynamic: list, gpu: list, num_cpu: int,
                amount_ram: float, amount_disk: float, num_gpu: int,
                num_jobs: int, job_duration: float, maxnodes: int, verbose: bool) -> dict:
    """
    Handles the checking for all node/slot types and invokes the output methods.

    Args:
        static: A list of static slot configurations
        dynamic: A list of dynamic slot configurations
        gpu: A list of gpu slot configurations
        num_cpu: The requested number of CPU cores
        amount_ram: The requested amount of RAM
        amount_disk: The requested amount of disk space
        num_gpu: The requested number of GPUs
        num_jobs: The amount of similar jobs to execute
        job_duration: The duration for each job to execute
        maxnodes: The maximum number of nodes to execute the jobs
        verbose: Flag to extend the output.

    Returns:

    """
    if verbose:
        pretty_print_input(num_cpu, amount_ram, amount_disk, num_gpu,
                           num_jobs, job_duration, maxnodes)

    preview_res = {'slots': [], 'preview': []}

    if num_cpu != 0 and num_gpu == 0:
        for node in dynamic:
            [node_dict, preview_node] = check_dynamic_slots(node, num_cpu,
                                                            amount_ram, job_duration, num_jobs)
            preview_res['slots'].append(node_dict)
            preview_res['preview'].append(preview_node)

        for node in static:
            [node_dict, preview_node] = check_static_slots(node, num_cpu,
                                                           amount_ram, job_duration, num_jobs)
            preview_res['slots'].append(node_dict)
            preview_res['preview'].append(preview_node)
    elif num_cpu != 0 and num_gpu != 0:
        for node in gpu:
            [node_dict, preview_node] = check_gpu_slots(node, num_cpu, num_gpu,
                                                        amount_ram, job_duration, num_jobs)
            preview_res['slots'].append(node_dict)
            preview_res['preview'].append(preview_node)
    else:
        return {}

    preview_res['preview'] = order_node_preview(preview_res['preview'])
    if maxnodes != 0 and len(preview_res['preview']) > maxnodes:
        preview_res['preview'] = preview_res['preview'][:maxnodes]

    if verbose:
        pretty_print_slots(preview_res)
    pretty_print_result(preview_res, verbose)

    return preview_res


def check_dynamic_slots(slot: dict, num_cpu: int, amount_ram: float,
                        job_duration: float, num_jobs: int) -> [dict, dict]:
    """
    Checks all dynamic slots if they fit the job.

    Args:
        slot: The slot to be checked for running the specified job.
        num_cpu: The number of CPU cores for a single job
        amount_ram: The amount of RAM for a single job
        job_duration: The duration for a single job to execute
        num_jobs: The number of similar jobs to be executed

    Returns:
        A dictionary of the checked slot and a dictionary with the occupancy details of the slot.
    """
    available_cores = slot["TotalSlotCpus"]
    node_dict = {'node': slot["UtsnameNodename"],
                 'type': slot["SlotType"],
                 'total_slots': str(slot["TotalSlots"]),
                 'cores': str(slot["TotalSlotCpus"]),
                 'disk': str(slot["TotalSlotDisk"]),
                 'ram': str(slot["TotalSlotMemory"])}

    # if the job fits, calculate and return the usage
    preview_node = {'name': slot["UtsnameNodename"],
                    'type': "dynamic",
                    'fits': 'NO',
                    'core_usage': '------',
                    'gpu_usage': '------',
                    'ram_usage': '------',
                    'sim_jobs': '------',
                    'wall_time_on_idle': 0}
    if num_cpu <= available_cores and amount_ram <= slot["TotalSlotMemory"]:
        preview_node['core_usage'] = str(num_cpu) + "/" + \
                                     str(slot["TotalSlotCpus"]) + " (" + \
                                     str(int(round((num_cpu / slot["TotalSlotCpus"]) * 100))) \
                                     + "%)"
        preview_node['ram_usage'] = "{0:.2f}".format(amount_ram) + "/" + \
                                    str(slot["TotalSlotMemory"]) + " GiB (" + \
                                    str(int(round((amount_ram / slot["TotalSlotMemory"]) * 100))) \
                                    + "%)"
        preview_node['fits'] = 'YES'
        preview_node['sim_jobs'] = min(int(available_cores / num_cpu),
                                       int(slot["TotalSlotMemory"] / amount_ram))
    else:
        preview_node['core_usage'] = str(num_cpu) + "/" + \
                                     str(slot["TotalSlotCpus"]) + " (" + str(
                                         int(round((num_cpu / slot["TotalSlotCpus"])
                                                   * 100))) + "%)"
        preview_node['sim_jobs'] = 0
        preview_node['ram_usage'] = "{0:.2f}".format(amount_ram) + "/" + str(
            slot["TotalSlotMemory"]) + " GiB (" \
            + str(int(round((amount_ram / slot["TotalSlotMemory"]) * 100))) + "%)"
        preview_node['fits'] = 'NO'

    if num_cpu <= slot["TotalSlotCpus"] and amount_ram <= slot["TotalSlotMemory"] \
            and job_duration != 0:
        cpu_fits = int(slot["TotalSlotCpus"] / num_cpu)
        jobs_parallel = cpu_fits \
            if amount_ram == 0 \
            else min(cpu_fits, int(slot["TotalSlotMemory"] / amount_ram))
        preview_node['wall_time_on_idle'] = str(math.ceil(num_jobs /
                                                          jobs_parallel) * job_duration)
    return [node_dict, preview_node]


def check_static_slots(slot: dict, num_cores: int, amount_ram: float,
                       job_duration: float, num_jobs: int) -> [dict, dict]:
    """
    Checks all static slots if they fit the job.

    Args:
        slot: The slot to be checked for running the specified job.
        num_cores: The number of CPU cores for a single job
        amount_ram: The amount of RAM for a single job
        job_duration: The duration for a single job to execute
        num_jobs: The number of similar jobs to be executed

    Returns:
        A dictionary of the checked slot and a dictionary with the occupancy details of the slot.
    """
    available_slots = slot["TotalSlotCpus"]
    node_dict = {'node': slot["UtsnameNodename"],
                 'type': slot["SlotType"],
                 'total_slots': str(slot["TotalSlots"]),
                 'cores': str(slot["TotalSlotCpus"]),
                 'disk': str(slot["TotalSlotDisk"]),
                 'ram': str(slot["TotalSlotMemory"])}

    # if the job fits, calculate and return the usage
    preview_node = {'name': slot["UtsnameNodename"],
                    'type': 'static',
                    'fits': 'NO',
                    'core_usage': '------',
                    'gpu_usage': '------',
                    'ram_usage': '------',
                    'sim_jobs': '------',
                    'wall_time_on_idle': 0}
    if num_cores <= slot["TotalSlotCpus"] and amount_ram <= slot["TotalSlotMemory"]:
        preview_node['core_usage'] = str(num_cores) + "/" + \
                                     str(slot["TotalSlotCpus"]) + " (" + str(
                                         int(round((num_cores / slot["TotalSlotCpus"])
                                                   * 100))) + "%)"
        preview_node['sim_jobs'] = available_slots
        preview_node['ram_usage'] = "{0:.2f}".format(amount_ram) + "/" + str(
            slot["TotalSlotMemory"]) + " GiB (" \
            + str(int(round((amount_ram / slot["TotalSlotMemory"]) * 100))) + "%)"
        preview_node['fits'] = 'YES'
        if job_duration != 0:
            cpu_fits = int(slot["TotalSlotCpus"] / num_cores)
            jobs_on_idle_slot = cpu_fits \
                if amount_ram == 0 \
                else min(cpu_fits, int(slot["TotalSlotMemory"] / amount_ram))
            preview_node['wall_time_on_idle'] = str(
                math.ceil(num_jobs / jobs_on_idle_slot / slot["TotalSlots"]) *
                job_duration)
    else:
        preview_node['core_usage'] = str(num_cores) + "/" + \
                                     str(slot["TotalSlotCpus"]) + " (" + str(
                                         int(round((num_cores / slot["TotalSlotCpus"])
                                                   * 100))) + "%)"
        preview_node['sim_jobs'] = 0
        preview_node['ram_usage'] = "{0:.2f}".format(amount_ram) + "/" + str(
            slot["TotalSlotMemory"]) + " GiB (" \
            + str(int(round((amount_ram / slot["TotalSlotMemory"]) * 100))) + "%)"
        preview_node['fits'] = 'NO'
    return [node_dict, preview_node]


def check_gpu_slots(slot: dict, num_cores: int, num_gpu: int, amount_ram: float,
                    job_duration: float, num_jobs: int) -> [dict, dict]:
    """
    Checks all gpu slots if they fit the job.

    Args:
        slot: The slot to be checked for running the specified job.
        num_cores: The number of CPU cores for a single job
        num_gpu: The number of GPU units for a single job
        amount_ram: The amount of RAM for a single job
        job_duration: The duration for a single job to execute
        num_jobs: The number of similar jobs to be executed

    Returns:
        A dictionary of the checked slot and a dictionary with the occupancy details of the slot.
    """
    available_slots = slot["TotalSlotCpus"]
    node_dict = {'node': slot["UtsnameNodename"],
                 'type': slot["SlotType"],
                 'total_slots': str(slot["TotalSlots"]),
                 'cores': str(slot["TotalSlotCpus"]),
                 'gpus': str(slot["TotalSlotGPUs"]),
                 'disk': str(slot["TotalSlotDisk"]),
                 'ram': str(slot["TotalSlotMemory"])}

    # if the job fits, calculate and return the usage
    preview_node = {'name': slot["UtsnameNodename"],
                    'type': 'gpu',
                    'fits': 'NO',
                    'gpu_usage': '------',
                    'core_usage': '------',
                    'ram_usage': '------',
                    'sim_jobs': '------',
                    'wall_time_on_idle': 0}
    if num_cores <= slot["TotalSlotCpus"] and amount_ram <= slot["TotalSlotMemory"] \
            and num_gpu <= slot["TotalSlotGPUs"]:
        preview_node['core_usage'] = str(num_cores) + "/" + \
                                     str(slot["TotalSlotCpus"]) + " (" + str(
                                         int(round((num_cores / slot["TotalSlotCpus"])
                                                   * 100))) + "%)"
        preview_node['gpu_usage'] = str(num_gpu) + "/" + \
            str(slot["TotalSlotGPUs"]) + " (" + str(
                int(round((num_gpu / slot["TotalSlotGPUs"])
                          * 100))) + "%)"
        preview_node['sim_jobs'] = min(int(slot["TotalSlotGPUs"] / num_gpu),
                                       int(available_slots / num_cores),
                                       int(slot["TotalSlotMemory"] / amount_ram))
        preview_node['ram_usage'] = "{0:.2f}".format(amount_ram) + "/" + str(
            slot["TotalSlotMemory"]) + " GiB (" \
            + str(int(round((amount_ram / slot["TotalSlotMemory"]) * 100))) + "%)"
        preview_node['fits'] = 'YES'
        if job_duration != 0:
            cpu_fits = int(slot["TotalSlotCpus"] / num_cores)
            gpu_fits = int(slot["TotalSlotGPUs"] / num_gpu)
            jobs_on_idle_slot = min(cpu_fits, gpu_fits) \
                if amount_ram == 0 \
                else min(min(cpu_fits, gpu_fits), int(slot["TotalSlotMemory"] / amount_ram))
            preview_node['wall_time_on_idle'] = str(
                math.ceil(num_jobs / jobs_on_idle_slot / slot["TotalSlotGPUs"]) *
                job_duration)
    else:
        preview_node['core_usage'] = str(num_cores) + "/" + \
                                     str(slot["TotalSlotCpus"]) + " (" + str(
                                         int(round((num_cores / slot["TotalSlotCpus"])
                                                   * 100))) + "%)"
        if slot["TotalSlotGPUs"] == 0:
            preview_node['gpu_usage'] = "No GPU ressource!"
        else:
            preview_node['gpu_usage'] = str(num_gpu) + "/" + \
                str(slot["TotalSlotGPUs"]) + " (" + str(
                    int(round((num_gpu / slot["TotalSlotGPUs"])
                              * 100))) + "%)"
        preview_node['sim_jobs'] = 0
        preview_node['ram_usage'] = "{0:.2f}".format(amount_ram) + "/" + str(
            slot["TotalSlotMemory"]) + " GiB (" \
            + str(int(round((amount_ram / slot["TotalSlotMemory"]) * 100))) + "%)"
        preview_node['fits'] = 'NO'
    return [node_dict, preview_node]


def order_node_preview(node_preview: list) -> list:
    """
    Order the list of checked nodes by fits/fits not and number of similar jobs descending.

    Args:
        node_preview: the list of checked nodes

    Returns:
        A list of checked nodes sorted by number of similar executable jobs.
    """
    return sorted(node_preview, key=lambda nodes: (nodes["sim_jobs"]), reverse=True)


def prepare_checking(cpu: int, gpu: int, ram: str, disk: str,
                     jobs: int, job_duration: str, maxnodes: int, verbose: bool) -> bool:
    """
    Loads the Slot configuration, handles storage and time inputs,
    and invokes the checking for given job request if the request is valid.

    Args:
        cpu: User input of CPU cores
        gpu: User input of GPU units
        ram: User input of the amount of RAM
        disk: User input of the amount of disk space
        jobs: User input of the number of similar jobs
        job_duration: User input of the duration time for a single job
        maxnodes:
        verbose:

    Returns:
        If all needed parameters were given
    """

    slot_config = define_slots()
    static_slts = filter_slots(slot_config, "static")
    dynamic_slts = filter_slots(slot_config, "dynamic")
    gpu_slts = filter_slots(slot_config, "gpu")

    [ram, ram_unit] = split_number_unit(ram)
    ram = calc_to_bin(ram, ram_unit)
    [disk, disk_unit] = split_number_unit(disk)
    disk = calc_to_bin(disk, disk_unit)

    [job_duration, duration_unit] = split_duration_unit(job_duration)
    job_duration = calc_to_min(job_duration, duration_unit)

    if cpu == 0:
        logging.warning("No number of CPU workers given --- ABORTING")
    elif ram == 0.0:
        logging.warning("No RAM amount given --- ABORTING")
    else:
        check_slots(static_slts, dynamic_slts, gpu_slts, cpu, ram, disk, gpu,
                    jobs, job_duration, maxnodes, verbose)
        return True

    return False


if __name__ == "__main__":
    CMD_ARGS = define_environment()
    CPU_WORKERS = CMD_ARGS.cpu
    if CPU_WORKERS is None:
        CPU_WORKERS = 0
    GPU_WORKERS = CMD_ARGS.gpu
    if GPU_WORKERS is None:
        GPU_WORKERS = 0

    RAM_AMOUNT = CMD_ARGS.ram
    DISK_SPACE = CMD_ARGS.disk

    JOB_AMOUNT = CMD_ARGS.jobs
    if JOB_AMOUNT is None:
        JOB_AMOUNT = 1
    JOB_DURATION = CMD_ARGS.time

    MATLAB_NODES = CMD_ARGS.maxnodes
    if MATLAB_NODES is None:
        MATLAB_NODES = 0

    # fetch current slot configuration
    FETCH_SLOTS = './fetch_condor_slots.py'
    os.system(FETCH_SLOTS)

    prepare_checking(CPU_WORKERS, GPU_WORKERS, RAM_AMOUNT, DISK_SPACE,
                     JOB_AMOUNT, JOB_DURATION, MATLAB_NODES, CMD_ARGS.verbose)
