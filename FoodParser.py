import json
import logging
import os
from collections import defaultdict

from timeit import default_timer as timer

with open('Raw_FoodValues.json', 'r') as f:
    data = json.load(f)

logger = logging.getLogger('FoodParser')
logging.basicConfig(filename='logs.info', level=logging.DEBUG)
separator = '\n--------------------------'

base_saturation = 0.6
entry_count = 0

cached_progress = 0
percentage_progress = 0

failed_entry = []
total_foodpoints = 0

start = timer()

food_dictionary = defaultdict(set)


def count_entries():
    global entry_count
    entry_count = (len([entries for entries in data.get('foods', [])]) + len([entries for entries in data.get('ingredients', [])]))


def successful_conversion(category):
    for group_name, entries in data.items():
        for entry in entries:

            if isinstance(entry[category], str):
                logger.info(f'Entry value for [{entry["name"]}] is not a number.')
                logger.info(f'Value = {entry[category]}')

                return False

            if isinstance(entry[category], list):
                if any(isinstance(element, str) for element in entry[category]):
                    
                    logger.info(f'Entry value for "{entry["name"]}" contains unconverted values.')
                    try:
                        missing_values = [item for item in entry[category] if isinstance(item, str)]
                        logger.info(f'"Unconverted values:" = {str(missing_values)}')
                    except KeyError as e:
                        logger.info(f'{category} entry cannot be found for this item.')

                else:
                    logger.info(f'Entry values found for "{entry["name"]}" have not yet been merged.')

                return False
    return True


def get_hunger_value(food_name):
    for group_name, entries in data.items():
        for entry in entries:
            if entry['name'] == food_name:
                if isinstance(entry['hunger'], int):
                    return entry['hunger']


def get_number_processes(food_name):
    if isinstance(food_name, str):
        for group_name, entries in data.items():
            for entry in entries:
                if entry['name'] == food_name:

                    if 'saturationModifier' in entry:
                        # If entry has numerical saturationModifier, return that
                        if isinstance(entry['saturationModifier'], float):
                            return entry['saturationModifier']

                        # If the entry has a single parent attempt processing:
                        elif isinstance(entry['saturationModifier'], list) and len(entry['saturationModifier']) == 1:
                            first_entry = entry['saturationModifier'][0]
                            recursive_first_entry = get_number_processes(first_entry)

                            if isinstance(first_entry, float):
                                return first_entry + base_saturation

                            elif isinstance(recursive_first_entry, float):
                                return get_number_processes(first_entry) + base_saturation
    return food_name


def translate_hunger_value(lst):
    modified_list = []
    for food in lst:
        if isinstance(food, str) and isinstance(get_hunger_value(food), int):
            modified_list.append(get_hunger_value(food))
        else:
            modified_list.append(food)
    return modified_list


def convert_to_saturation_score(lst):
    modified_list = []
    for food in lst:
        calculated_value = get_number_processes(food)
        if isinstance(food, str) and isinstance(calculated_value, float):
            modified_list.append(calculated_value)
        else:
            modified_list.append(food)
    return modified_list


def process_saturation_entries(json_data, iterations):
    processed_entries_saturation = 0

    for group_name, entries in json_data.items():
        for entry in entries:
            if 'saturationModifier' not in entry:

                if 'hunger' in entry:
                    if isinstance(entry['hunger'], list):
                        entry['saturationModifier'] = entry['hunger']
                    else:
                        entry['saturationModifier'] = 0
            else:
                if isinstance(entry['saturationModifier'], int) and 'hunger' in entry and isinstance(entry['hunger'], int):
                    continue

                if isinstance(entry['saturationModifier'], list):

                    if all(isinstance(element, float) for element in entry['saturationModifier']):
                        Bonus = base_saturation

                        # If it is a smelting process we do not give bonuses
                        if -1.0 in entry['saturationModifier']:
                            entry['saturationModifier'].remove(-1.0)
                            Bonus = 0

                        # average_saturation_modifier = sum()/len(entry['saturationModifier'])
                        # entry['saturationModifier'] = round(average_saturation_modifier + Bonus, 1)

                        entry['saturationModifier'] = round(max(entry['saturationModifier']) + Bonus, 1)

                        processed_entries_saturation += 1

                if isinstance(entry['saturationModifier'], list):

                    if any(isinstance(element, str) for element in entry['saturationModifier']):
                        entry['saturationModifier'] = convert_to_saturation_score(entry['saturationModifier'])

    logger.info(f'Processed {processed_entries_saturation} saturation entries this cycle.')
    if successful_conversion('saturationModifier'):
        logger.info(f'Success!')
        logger.info(f'Completed saturation entries in {iterations} cycles')
    else:
        logger.info('Continuing...')
        process_saturation_entries(json_data, iterations + 1)


def process_hunger_entries(json_data, iterations):
    processed_entries_hunger = 0

    for group_name, entries in json_data.items():
        for entry in entries:
            if isinstance(entry['hunger'], list):
                if all(isinstance(element, int) for element in entry['hunger']):
                    # Sum hunger entries
                    hunger_modifier = 1 if 'hungerModifier' not in entry else entry['hungerModifier']
                    sum_hunger = sum(entry['hunger'])

                    # We want entries with a value of exactly 0 to remain 0
                    # else we give it a minimum of 1
                    entry['hunger'] = max(int(sum_hunger * hunger_modifier), 1) if not sum_hunger == 0 else 0

                    processed_entries_hunger += 1

            if isinstance(entry['hunger'], list):
                if any(isinstance(element, str) for element in entry['hunger']):
                    # Translate strings into values
                    entry['hunger'] = translate_hunger_value(entry['hunger'])

    logger.info(f'Processed {processed_entries_hunger} hunger entries this cycle.')

    if successful_conversion('hunger'):
        logger.info(f'Success!')
        logger.info(f'Completed hunger entries in {iterations} cycles')
    else:
        logger.info('Continuing...')
        process_hunger_entries(json_data, iterations+1)


def successful_group_food_conversion():
    for group_name, entries in data.items():
        for entry in entries:
            if 'foodGroups' not in entry or not isinstance(entry['foodGroups'], list) or any(":" in element for element in entry['foodGroups']):
                logger.info(f'Entry "{entry["name"]}" does not appear to have been fully converted:')
                try:
                    missing_conversions = [item for item in entry['foodGroups'] if ":" in item]
                    logger.info(f'"Invalid conversions:" = {str(missing_conversions)}')
                except KeyError as e:
                    logger.info('"foodGroups" entry cannot be found for this item.')

                return False
    return True


def replace_entries(input_list, mapping_dict):
    result_set = set()

    for item in input_list:
        values = mapping_dict.get(item, [item])
        result_set.update(filter(lambda x: x != 'None', values))

    return list(result_set)


def process_food_groups(json_data, iterations):
    processed_group_food = 0
    for group_name, entries in json_data.items():
        # Save to dictionary
        for entry in entries:
            if 'foodGroups' in entry:
                if isinstance(entry['foodGroups'], list):
                    if not any(":" in element for element in entry['foodGroups']):
                        food_dictionary[entry['name']] |= set(entry['foodGroups'])

        # Create list to be processed into food values
        for entry in entries:
            if 'foodGroups' not in entry:
                if 'hunger' in entry:
                    if isinstance(entry['hunger'], list):
                        entry['foodGroups'] = entry['hunger']
                    else:
                        entry['foodGroups'] = ['None']

        # Replace values with dictionary
        for entry in entries:
            if 'foodGroups' in entry:
                if isinstance(entry['foodGroups'], list):
                    if any(":" in element for element in entry['foodGroups']):
                        entry['foodGroups'] = replace_entries(entry['foodGroups'], food_dictionary)
                        if not any(":" in element for element in entry['foodGroups']):
                            processed_group_food += 1

        # Process additions or deletions
        for entry in entries:
            if 'appendGroups' in entry:
                if isinstance(entry['appendGroups'], list):
                    entry['foodGroups'] = list(set(entry['foodGroups'] + entry['appendGroups']))
            if 'removeGroups' in entry:
                if isinstance(entry['removeGroups'], list):
                    entry['foodGroups'] = list(filter(lambda x: x not in entry['removeGroups'], entry['foodGroups']))

    logger.info(f'Processed {processed_group_food} food group entries this cycle.')

    if successful_group_food_conversion():
        logger.info(f'Success!')
        logger.info(f'Completed foodGroups entries in {iterations} cycles')
    else:
        logger.info('Continuing...')
        process_food_groups(json_data, iterations+1)


def output_food_groups():
    food_groups = set()
    colors = {
        "Beverages": "dark_aqua",
        "Dairy": "white",
        "Seafood": "aqua",
        "Fruits": "dark_blue",
        "Fungi": "light_purple",
        "Grains": "yellow",
        "Legumes": "red",
        "Meats": "dark_red",
        "Nuts": "dark_gray",
        "Sweets": "gold",
        "Vegetables": "green",
        "Herbs & Spices": "dark_green",
    }
    for entry in data['foods']:
        for food_group in entry['foodGroups']:
            if food_group != 'None':
                food_groups.add(food_group)

    for food_group in food_groups:
        group_json = {
            "food": {
                "items": []
            },
            "name": food_group,
            "color": colors[food_group] if colors.get(food_group) is not None else ""
        }

        for entry in data['foods']:
            if food_group in entry['foodGroups']:
                item = entry['name'] if entry['meta'] == 0 else f"{entry['name']}:{entry['meta']}"
                group_json["food"]["items"].append(item)

        directory = './output/SpiceOfLife/'

        # Checks if output folder exists, else attempts to create one
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
        except Exception as e:
            print(f"An error occurred: {e}")

        # saves data in the output folder
        with open(directory + food_group, 'w') as output:
            json.dump(group_json, output, indent=4)


def get_total_food_points():
    global total_foodpoints

    for entry in data['foods']:
        total_foodpoints += entry["hunger"]


def initiate(json_data):
    process_food_groups(json_data, 0)
    process_saturation_entries(json_data, 0)
    process_hunger_entries(json_data, 0)


# Cleans up json file from unnecessary fields and entries
def clean_data(json_data):
    clean_entries = 0

    foods_only_data = {'foods': [item for item in json_data.get('foods', [])]}

    for entry in foods_only_data['foods']:
        entries_to_delete = ['appendGroups', 'removeGroups']

        for deletion in entries_to_delete:
            if deletion in entry:
                del entry[deletion]

        clean_entries += 1

    return foods_only_data


# Save new Json data
def output_data(json_file, title):
    directory = './output/'

    # Checks if output folder exists, else attempts to create one
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
    except Exception as e:
        print(f"An error occurred: {e}")

    # saves data in the output folder
    with open(directory + title, 'w') as output:
        json.dump(json_file, output, indent=4)


count_entries()
initiate(data)
get_total_food_points()
output_food_groups()

output_data(clean_data(data), 'Food Values.json')

end = timer()

print('Completed!')
print('Processed ' + str(entry_count) + ' food entries in ' + str(round(end - start, 3)) + ' seconds')
print(f'Total food points: {total_foodpoints}')
