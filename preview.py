import argparse
from tabulate import tabulate


def define_environment():
    parser = argparse.ArgumentParser(description="To get a preview for any job you are trying to execute using "
                                                 "HTCondor, please pass at least either the number of CPUs or GPUs and "
                                                 "either the amount of RAM or diskspace to this script according to "
                                                 "the usage example shown above.")
    parser.add_argument("-v", "--verbose", help="Print extended log to stdout", action='store_true')
    parser.add_argument("-c", "--cpu", help="Set number of requested CPU Cores", type=int)
    parser.add_argument("-g", "--gpu", help="Set number of requested GPU Units", type=int)
    parser.add_argument("-d", "--disk", help="Set amount of requested disk storage in GB", type=int)
    parser.add_argument("-r", "--ram", help="Set amount of requested memory storage in GB", type=int)

    p = parser.parse_args()
    return p


# a collection of slots will be defined as a list of dictionarys for each different slot configuration
def define_slots():
    #  define all existing static slot configurations
    static_slots = [{"node": "cpu1", "total_slots": 32, "total_ram": 500, "slots_in_use": 0, "ram_in_use": 0,
                     "single_slot": {"cpu_cores": 1, "ram_amount": 15}}]

    #  define all existing partitionable configurations
    partitionable_slots = [{"node": "cpu2", "total_cores": 32, "total_ram": 500, "cores_blocked": 0, "ram_blocked": 0}]

    return static_slots, partitionable_slots


def pretty_print_input(num_cpu, amount_ram, amount_disk, num_gpu):
    #  print out what the user gave as input
    data = [['CPUS', str(num_cpu)], ['RAM', str(amount_ram) + " GB"], ['STORAGE', str(amount_disk) + " GB"],
            ['GPUS', str(num_gpu)]]
    print("---------------------- INPUT ----------------------")
    print(tabulate(data, headers=["Parameter", "Input Value"]) + "\n\n")


def pretty_print_slots(result):
    #  print out what the result is
    data = []
    for node in result['nodes']:
        row = [node['name'], node['type'], str(node['workers']), str(node['ram'])]
        if node['type'] == "static":
            row.append(str(node['slot_cores']))
            row.append(str(node['slot_ram']))
        else:
            row.append("------")
            row.append("------")
        row.append(str(node['slot_free']))
        row.append(str(node['ram_free']))
        data.append(row)

    print("---------------------- NODES ----------------------")
    print(tabulate(data, headers=["Node", "Slot Type", "Total Cores/Slots", "Total RAM",
                                  "Single Slot Cores", "Single Slot RAM", "Cores/Slots free", "RAM free"]) + "\n\n")

    data = []
    for node in result['preview']:
        row = [node['name'], node['type'], node['fits'], node['cpu_usage'], node['ram_usage'], str(node['sim_jobs'])]
        data.append(row)

    print("---------------------- PREVIEW ----------------------")
    print(tabulate(data, headers=["Node", "Slot type", "Job fits", "Core usage",
                                  "RAM usage", "Amount of similar jobs"]) + "\n\n")


def check_slots(static, dynamic, gpu, num_cpu=0, amount_ram=0, amount_disk=0, num_gpu=0):
    pretty_print_input(num_cpu, amount_ram, amount_disk, num_gpu)

    preview_res = {'nodes': [], 'preview': []}

    if num_cpu != 0:
        #  Check all DYNAMIC nodes
        for node in dynamic:
            available_cores = node["total_cores"] - node["cores_blocked"]
            available_ram = node["total_ram"] - node["ram_blocked"]
            node_dict = {'name': node["node"],
                         'type': 'dynamic',
                         'workers': str(node["total_cores"]),
                         'ram': str(node["total_ram"]) + " GB",
                         'slot_free': str(available_cores),
                         'ram_free': str(available_ram) + " GB"}
            preview_res['nodes'].append(node_dict)
            # if the job fits, calculate and return the usage
            preview_node = {'name': node["node"], 'type': 'dynamic', 'fits': 'NO',
                            'core_usage': '------', 'ram_usage': '------', 'sim_jobs': '------'}
            if num_cpu <= available_cores and amount_ram <= available_ram:
                preview_node['core_usage'] = str(num_cpu)+"/"+str(node["total_cores"])+" (" + \
                                            str(int(round((num_cpu / node["total_cores"]) * 100))) + "%)"
                preview_node['ram_usage'] = str(amount_ram)+"/"+str(node["total_ram"])+" GB (" + \
                                            str(int(round((amount_ram / node["total_ram"]) * 100))) + "%)"
                preview_node['fits'] = 'YES'
                preview_node['sim_jobs'] = str(int(available_cores / num_cpu) - 1)
            preview_res['preview'].append(preview_node)

        #  Check all STATIC nodes
        for node in static:
            available_slots = node["total_slots"] - node["slots_in_use"]
            single_slot = node["single_slot"]
            node_dict = {'name': node["node"], 'type': 'static',
                         'workers': str(node["total_slots"]),
                         'ram': str(node["total_ram"]) + " GB",
                         'slot_cores': str(single_slot["cores"]),
                         'slot_ram': str(single_slot["ram_amount"]) + " GB",
                         'slot_free': str(available_slots),
                         'ram_free': '---'}
            preview_res['nodes'].append(node_dict)
            # if the job fits, calculate and return the usage
            preview_node = {'name': node["node"],
                            'type': 'static',
                            'fits': 'NO',
                            'core_usage': '------',
                            'ram_usage': '------',
                            'sim_jobs': '------'}
            if num_cpu <= single_slot["cores"] and amount_ram <= single_slot["ram_amount"]:
                #  On STATIC nodes it's like ALL or NOTHING, when there are more than one CPUs requested
                preview_node['core_usage'] = str(num_cpu)+"/"+str(single_slot["cores"])+" ("+str(
                    int(round((num_cpu / single_slot["cores"]) * 100)) if num_cpu == 1 else 0) + "%)"
                preview_node['sim_jobs'] = str(int(available_slots - num_cpu) if num_cpu == 1 else 0)
                preview_node['ram_usage'] = str(amount_ram)+"/"+str(single_slot["ram_amount"])+" GB ("+str(
                    int(round((amount_ram / single_slot["ram_amount"]) * 100)) if num_cpu == 1 else 0) + "%)"
                preview_node['fits'] = 'YES'
            preview_res['preview'].append(preview_node)
    elif num_gpu != 0:
        #  Check all GPU nodes
        for node in gpu:
            available_slots = node["total_slots"] - node["slots_in_use"]
            single_slot = node["single_slot"]
            node_dict = {'name': node["node"], 'type': 'gpu/static',
                         'workers': str(node["total_slots"]),
                         'ram': str(node["total_ram"]) + " GB",
                         'slot_cores': str(single_slot["cores"]),
                         'slot_ram': str(single_slot["ram_amount"]) + " GB",
                         'slot_free': str(available_slots),
                         'ram_free': '---'}
            preview_res['nodes'].append(node_dict)
            # if the job fits, calculate and return the usage
            preview_node = {'name': node["node"],
                            'type': 'gpu',
                            'fits': 'NO',
                            'core_usage': '------',
                            'ram_usage': '------',
                            'sim_jobs': '------'}
            if num_gpu <= single_slot["cores"] and amount_ram <= single_slot["ram_amount"]:
                #  On STATIC nodes it's like ALL or NOTHING, when there are more than one CPUs requested
                preview_node['core_usage'] = str(num_gpu) + "/" + str(single_slot["cores"]) + " (" + str(
                    int(round((num_gpu / single_slot["cores"]) * 100)) if num_gpu == 1 else 0) + "%)"
                preview_node['sim_jobs'] = str(int(available_slots - num_gpu) if num_gpu == 1 else 0)
                preview_node['ram_usage'] = str(amount_ram) + "/" + str(single_slot["ram_amount"]) + " GB (" + str(
                    int(round((amount_ram / single_slot["ram_amount"]) * 100)) if num_gpu == 1 else 0) + "%)"
                preview_node['fits'] = 'YES'
            preview_res['preview'].append(preview_node)

    pretty_print_slots(preview_res)


if __name__ == "__main__":
    static_slots, dynamic_slots, gpu_slots = define_slots()
    args = define_environment()

    CPU = args.cpu
    if CPU is None:
        CPU = 0
    GPU = args.gpu
    if GPU is None:
        GPU = 0
    RAM = args.ram
    if RAM is None:
        RAM = 0
    DISK = args.disk
    if DISK is None:
        DISK = 0

    if args.verbose:
        print("verbosity turned on")
    if CPU == 0 and GPU == 0:
        print("No number of CPU or GPU workers given --- ABORTING")
    elif RAM == 0 and DISK == 0:
        print("No RAM or DISK amount given --- ABORTING")
    else:
        check_slots(static_slots, dynamic_slots, gpu_slots, CPU, RAM, DISK, GPU)
        print("Check finished!")
