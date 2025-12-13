import json
import logging
import os
from collections import defaultdict

from timeit import default_timer as timer

open('logs.info', 'w').close()

with open('Raw_FoodValues.json', 'r') as f:
    data = json.load(f)

logger = logging.getLogger('FoodParser')
logging.basicConfig(filename='logs.info', level=logging.DEBUG)
separator = '\n--------------------------'

base_saturation = 0.2

bonus_smelting = 2
bonus_saturation = 0.6
incompatible_with_saturation_bonus = ["smelting", "inheritance"]

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


def is_conversion_complete(category):
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


def retrieve_saturation_score(food_name, food_meta):
    if isinstance(food_name, str):
        for group_name, entries in data.items():

            for entry in entries:
                if entry['name'] == food_name:
                    logger.info(f'Found target food {food_name}, processing entry')

                    if 'meta' in entry:
                        if entry['meta'] != food_meta:
                            # Entry has a Metadata but doesn't match with our target's. Skipping Entry
                            continue
                    elif food_meta > 0:
                        # Target has a specified Metadata but Entry has no Metadata. Skipping Entry
                        continue

                    if 'saturationModifier' in entry:
                        logger.info(f"Found entries for {food_name}: {entry['saturationModifier']}")

                        # If entry has numerical saturationModifier, return that
                        if isinstance(entry['saturationModifier'], float):
                            logger.info(f'Entry is already numerical. Using that')
                            return float(max(entry['saturationModifier'], base_saturation))


                        # If the entry has saturation Modifier as list
                        if isinstance(entry['saturationModifier'], list):
                            logger.info(f"Entry is list...")
                            if all(isinstance(element, float) for element in entry['saturationModifier']):
                                finalize_saturation_score(entry)
                            else:
                                for component in entry['saturationModifier']:
                                    if not isinstance(component, float):
                                        component_name = get_food_name(component)
                                        component_meta = get_food_meta(component)
                                        retrieve_saturation_score(component_name, component_meta)

                    logger.info(f'Failed to convert {food_name} into numerical')
                    logger.info(f'Could not parse {entry["saturationModifier"]} into numerical value. We will try again later.')

    return food_name


def translate_hunger_value(lst):
    modified_list = []
    for food in lst:
        if isinstance(food, str) and isinstance(get_hunger_value(food), int):
            modified_list.append(get_hunger_value(food))
        else:
            modified_list.append(food)
    return modified_list

def get_food_name(food):
    name = food

    # Can be split in 3 parts using ":" (aka contains modID:name:meta)
    if len(food.rsplit(":")) == 3:
        # split "modID:name" from "meta"
        name = food.rsplit(":", 1)[0]

    return name

def get_food_meta(food):
    meta = 0

    # Can be split in 3 parts using ":" (aka contains modID:name:meta)
    if len(food.rsplit(":")) == 3:
        # split "modID:name" from "meta"
        meta = food.rsplit(":", 1)[1]

    return meta


def convert_list_to_numerical_saturation(food_list):
    number_list = []
    for food_entry in food_list:
        if isinstance(food_entry, str):
            # Name entry found.Attempting to retrieve its Saturation Value
            food_name = get_food_name(food_entry)
            food_meta = get_food_meta(food_entry)

            calculated_value = retrieve_saturation_score(food_name, food_meta)
            if isinstance(calculated_value, float):
                # Successfully converted Food Entry into saturation score
                number_list.append(calculated_value)

            else:
                # Failed to convert Food Entry into saturation score. We'll try again later.
                number_list.append(food_entry)

        elif isinstance(food_entry, float):
            # Entry is already converted into numerical value
            number_list.append(food_entry)

        else:
            raise KeyError(
                logger.info('"foodGroups" Attempted to convert food list with an invalid list.'),
                logger.info(f"Errored entry: {food_entry} in {food_list}")
            )


    return number_list


def finalize_saturation_score(entry):
    Bonus = bonus_saturation

    # For Debug Purposes
    entry['componentSaturations'] = entry['saturationModifier']
    #####

    # Top Saturation Score in list
    top_score = max(entry['saturationModifier'])

    # Factor in Minimum Saturation and Saturation Bonuses
    if 'type' in entry and entry['type'] in incompatible_with_saturation_bonus:
        Bonus = 0

    final_score = max(top_score, base_saturation) + Bonus

    entry['saturationModifier'] = float(round(final_score, 1))

def sanitize_saturation_entries(json_data):
    for group_name, entries in json_data.items():
        for entry in entries:
            if 'saturationModifier' not in entry:

                # Entry does not have a SaturationModifier prepared.
                if 'hunger' in entry:

                    # Compute [saturationModifier] from ingredient list in [hunger]
                    if isinstance(entry['hunger'], list):
                        entry['saturationModifier'] = entry['hunger']

                        # Debug Entry Things - ignore
                        entry['componentItems'] = entry['hunger']

                    else:
                        # SaturationModifier set to default
                        entry['saturationModifier'] = base_saturation


def process_saturation_entries(json_data, iterations):
    processed_entries_saturation = 0

    for group_name, entries in json_data.items():
        for entry in entries:

            # Found manually compiled numerical entry without decimal. We'll use that
            if isinstance(entry['saturationModifier'], int):
                entry['saturationModifier'] = float(entry['saturationModifier'])

            # Found an instance of 'saturationModifier' in an inconverted state
            elif isinstance(entry['saturationModifier'], list):
                logger.info(f"Found List: {entry['saturationModifier']}")


                # Check if conversion was complete to attempt finalization.
                if all(isinstance(element, float) for element in entry['saturationModifier']):
                    # Finalizing ['saturationModifier']
                    finalize_saturation_score(entry)
                    logger.info(f"Successfully processed Entry {entry['name']}.")

                    processed_entries_saturation += 1

                # Attempt numeric conversion for ['saturationModifier'] if needed
                if isinstance(entry['saturationModifier'], list):
                    if not all(isinstance(element, float) for element in entry['saturationModifier']):
                        # Converting ['saturationModifier'] list into numerical values. . .
                        for element in entry['saturationModifier']:
                            if not isinstance(element, float):
                                entry['saturationModifier'] = convert_list_to_numerical_saturation(
                                    entry['saturationModifier'])
                    else:
                        logger.info(f"List is NOT numeric")


                # Check conversion status for entry
                if not isinstance(entry['saturationModifier'], float):
                    logger.info(
                        f"Incomplete process Entry for {entry['name']}. Contains: {entry['saturationModifier']}.")

            elif not isinstance(entry['saturationModifier'], float):
                logger.info(f'Found invalid saturationModifier for {entry["name"]}')
                logger.info(f'Type = {type(entry["name"])}')

    logger.info(f'Processed {processed_entries_saturation} saturation entries this cycle.')

    if is_conversion_complete('saturationModifier'):
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
                    hunger_bonus = bonus_smelting if 'type' in entry and entry['type'] == 'smelting' else 0

                    value_hunger = sum(entry['hunger']) + hunger_bonus

                    # We want entries with a value of exactly 0 to remain 0
                    # else we give it a minimum of 1
                    entry['hunger'] = max(int(value_hunger * hunger_modifier), 1) if not value_hunger == 0 else 0

                    processed_entries_hunger += 1

            if isinstance(entry['hunger'], list):
                if any(isinstance(element, str) for element in entry['hunger']):
                    # Translate strings into values
                    entry['hunger'] = translate_hunger_value(entry['hunger'])

    logger.info(f'Processed {processed_entries_hunger} hunger entries this cycle.')

    if is_conversion_complete('hunger'):
        logger.info(f'Success!')
        logger.info(f'Completed hunger entries in {iterations} cycles')
    else:
        logger.info(f'Conversion incomplete. Continuing...')
        process_hunger_entries(json_data, iterations+1)


def successful_food_groups_conversion():
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

def get_food_name_with_meta(entry):
    food_meta = entry['meta'] if 'meta' in entry else 0
    return entry['name'] + ":" + str(food_meta)

def initiate_food_group_list_from_ingredients(ingredients):
    food_group_list = []
    for entry in ingredients:

        entry_parts = len(entry.rsplit(":"))

        if entry_parts == 3:
            # Entry contains "modID:name:meta"
            food_group_list.append(entry)
        elif entry_parts == 2:
            # Entry contains "modID:name" but it is missing "meta"
            food_group_list.append(entry + ":" + str(0))
        else:
            raise KeyError(
                logger.info(f'"hunger" list contains invalid entry: { entry }')
            )


    return food_group_list

def process_food_groups(json_data, iterations):
    processed_group_food = 0
    for group_name, entries in json_data.items():
        # Generate initial food dictionary from entries with an already defined food group
        for entry in entries:
            if 'foodGroups' in entry:
                if isinstance(entry['foodGroups'], list):
                    if not any(":" in element for element in entry['foodGroups']):
                        food_dictionary[get_food_name_with_meta(entry)] |= set(entry['foodGroups'])

        # Generate missing list for entries that require it
        for entry in entries:
            if 'foodGroups' not in entry:
                if 'hunger' in entry:
                    if isinstance(entry['hunger'], list):
                        entry['foodGroups'] = initiate_food_group_list_from_ingredients(entry['hunger'])
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
            if 'foodGroups' in entry:
                if 'appendGroups' in entry:
                    if isinstance(entry['appendGroups'], list):
                        entry['foodGroups'] = list(set(entry['foodGroups'] + entry['appendGroups']))
                if 'removeGroups' in entry:
                    if isinstance(entry['removeGroups'], list):
                        entry['foodGroups'] = list(
                            filter(lambda x: x not in entry['removeGroups'], entry['foodGroups']))
                # Make it tidy
                entry['foodGroups'] = sorted(entry['foodGroups'])

    logger.info(f'Processed {processed_group_food} food group entries this cycle.')

    if successful_food_groups_conversion():
        logger.info(f'Success!')
        logger.info(f'Completed foodGroups entries in {iterations} cycles')
    else:
        logger.info('Continuing...')
        process_food_groups(json_data, iterations+1)


def export_food_groups():
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
        with open(directory + food_group + ".json", 'w') as output:
            json.dump(group_json, output, indent=4)


def get_total_food_points():
    global total_foodpoints

    for entry in data['foods']:
        total_foodpoints += entry["hunger"]

def get_number_foods_per_quality(index):
    count = 0

    if index == 0:
        for entry in data['foods']:
            if 0.6 > entry['saturationModifier']:
                count += 1
    if index == 1:
        for entry in data['foods']:
            if 1.2 > entry['saturationModifier'] >= 0.6:
                count += 1

    if index == 2:
        for entry in data['foods']:
            if 1.8 > entry['saturationModifier'] >= 1.2:
                count += 1

    if index == 3:
        for entry in data['foods']:
            if 2.4 > entry['saturationModifier'] >= 1.8:
                count += 1
    if index == 4:
        for entry in data['foods']:
            if entry['saturationModifier'] >= 2.4:
                count += 1

    return count



def initiate(json_data):
    process_food_groups(json_data, 0)
    sanitize_saturation_entries(json_data)
    process_saturation_entries(json_data, 0)
    process_hunger_entries(json_data, 0)


# Cleans up json file from unnecessary fields and entries
def clean_data(json_data):
    clean_entries = 0

    foods_only_data = {'foods': [item for item in json_data.get('foods', [])]}

    for entry in foods_only_data['foods']:
        entries_to_delete = ['foodGroups', 'hungerModifier', 'appendGroups', 'removeGroups', 'componentItems', 'componentSaturations', 'type']

        for deletion in entries_to_delete:
            if deletion in entry:
                del entry[deletion]

        clean_entries += 1

    return foods_only_data


# Save new Json data
def output_data(json_file, title):
    directory = './output/HungerOverhaul/'

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
export_food_groups()

output_data(data, 'DEBUG-Food Values.json')
output_data(clean_data(data), 'Food Values.json')

end = timer()

print('Completed!')
print('Processed ' + str(entry_count) + ' food entries in ' + str(round(end - start, 3)) + ' seconds')
print(f'Total food points: {total_foodpoints}')
print(f'Poor Foods (<0.2): {get_number_foods_per_quality(0)}')
print(f'Low Foods (<0.6): {get_number_foods_per_quality(1)}')
print(f'Normal Foods (<1.2): {get_number_foods_per_quality(2)}')
print(f'Good Foods (<1.8): {get_number_foods_per_quality(3)}')
print(f'Great Foods (+2.4): {get_number_foods_per_quality(4)}')
