from typing import List, Tuple, Union
from sqlalchemy import true
from annotinder.models import Unit, Annotation


def default_conditionals(unit_type: str) -> Tuple[str, str, str, float]:
    successAction = None
    failAction = None
    message = None
    damage = 0
    if unit_type == 'train':
        successAction = "applaud"
        failAction = "retry"
        message = "### Please retry.\n\nThis is a **training** unit, and the answer you gave was incorrect. \nPlease have another look, and select a different answer"
    if unit_type == 'screen':
        failAction = "block"
        message = "### Thank you for participating.\n\nBased on your answer for this question we determined that you do not meet the qualifications for this coding job.\nWe sincerely thank you for your time."
    if unit_type == 'test':
        damage = 10
    return successAction, failAction, message, damage


def check_conditionals(unit: Unit, annotation: dict, report_success=True) -> Tuple[float, dict]:
    """
    If unit has conditions, see if annotations satisfy them.
    This can various consequences:
    - The coder can take damage for getting it wrong.
    - The coder can receive feedback. The unit will then be marked
      as IN_PROGRESS, and the coder can't continue before the right answer is given
    """
    damage = 0
    evaluation = {}
    if unit.conditionals is None:
        return damage, evaluation

    defaultSuccessAction, defaultFailAction, defaultMessage, defaultDamage = default_conditionals(
        unit.unit_type)

    for conditional in unit.conditionals:
        if conditional['variable'] not in evaluation:
            evaluation[conditional['variable']] = {}

        variable_coded = False
        success = True
        submessages = []

        validAnnotation = {}
        found_match = False
        for c in conditional['conditions']:
            for i, a in enumerate(annotation):
                if conditional['variable'] != a['variable']:
                    continue
                if i not in validAnnotation:
                    validAnnotation[i] = False
                variable_coded = True
                if 'field' in c:
                    if c['field'] != a['field']:
                        continue
                if 'offset' in c:
                    if c['offset'] != a['offset']:
                        continue
                if 'length' in c:
                    if c['length'] != a['length']:
                        continue

                op = c.get('operator', '==')

                if op == "==" and a['value'] == c['value']:
                    found_match = True
                if op == "<=" and a['value'] <= c['value']:
                    found_match = True
                if op == "<" and a['value'] < c['value']:
                    found_match = True
                if op == ">=" and a['value'] >= c['value']:
                    found_match = True
                if op == ">" and a['value'] > c['value']:
                    found_match = True
                if op == "!=" and a['value'] != c['value']:
                    found_match = True
                if found_match:
                    validAnnotation[i] = True
                    continue
            if found_match:
                continue
            if not variable_coded:
                continue

            success = False
            damage += c.get('damage', 0)
            if 'submessage' in c:
                submessages.append(c['submessage'])

        correctAnnotation = [annotation[k]
                             for k, v in validAnnotation.items() if v]
        incorrectAnnotation = [annotation[k]
                               for k, v in validAnnotation.items() if not v]
        if len(incorrectAnnotation) > 0:
            success = False

        if success:
            if report_success:
                evaluation[conditional['variable']]['action'] = conditional.get(
                    'onSuccess', defaultSuccessAction)
        else:
            evaluation[conditional['variable']]['action'] = conditional.get(
                'onFail', defaultFailAction)
            evaluation[conditional['variable']]['message'] = conditional.get(
                'message', defaultMessage)
            evaluation[conditional['variable']]['submessages'] = submessages
            evaluation[conditional['variable']]['correct'] = correctAnnotation
            evaluation[conditional['variable']]['incorrect'] = incorrectAnnotation

            damage += conditional.get('damage', defaultDamage)
    return damage, evaluation


def invalid_conditionals(unit: Unit, codebook: dict) -> List:
    """
    Check if conditionals are possible given the unit and codebook.
    This check is performed when uploading a codingjob, to prevent deploying
    jobs where coders can get stuck due to impossible conditionals.
    Return an array of variable names for which the conditional failed
    """
    invalid_variables = []

    if unit.conditionals is None:
        return invalid_variables
    if 'codebook' in unit.unit:
        # if unit has a specific codebook, use this instead of the jobset codebook
        codebook = unit.unit['codebook']

    for conditional in unit.conditionals:
        if not position_is_possible(conditional['conditions'], unit):
            invalid_variables.append(conditional['variable'])
            continue
        if codebook['type'] == 'questions':
            if not valid_questions_conditionals(conditional['variable'], conditional['conditions'], codebook['questions']):
                invalid_variables.append(conditional['variable'])
        if codebook['type'] == 'annotate':
            if not valid_annotate_conditionals(conditional['variable'], conditional['conditions'], codebook['variables']):
                invalid_variables.append(conditional['variable'])

    return invalid_variables


def valid_questions_conditionals(variable, conditions, questions):
    """
    Check conditionals for 'questions' type codebook
    """
    for question in questions:
        code_values = get_code_values(question.get('codes', []))
        if variable == question['name']:
            if value_is_possible(conditions, code_values):
                return True

        for item in question.get('items', []):
            if variable == question['name'] + '.' + item['name']:
                if question['type'] == 'inputs':
                    if input_is_possible(conditions, item):
                        return True
                else:
                    if value_is_possible(conditions, code_values):
                        return True
    return False


def valid_annotate_conditionals(variable, conditions, variables):
    """
    Check conditionals for 'annotation' type codebook
    """
    for v in variables:
        code_values = get_code_values(question.get('codes', []))
        if variable == v['name']:
            if value_is_possible(conditions, code_values):
                return True

    return False


def get_code_values(codes):
    """
    codes can be an array of dictionaries that have a 'code' key (and other details), 
    or a simple array of strings, in which case the string is the code.
    """
    values = []
    for code in codes:
        if isinstance(code, dict):
            values.append(code['code'])
        else:
            values.append(code)
    return values


def get_conditions(conditions):
    """
    conditions can be an array of dictionaries, that have a 'value' 
    """


def value_is_possible(conditions, values):
    """
    Check whether a condition is possible given an array of values
    """
    for condition in conditions:
        has_match = False
        condition_value = get_condition_value(condition)
        operator = condition.get('operator', '==')
        for value in values:
            if isinstance(condition_value, float):
                try:
                    value = float(value)
                except:
                    continue
            if operator == '==' and value == condition_value:
                has_match = True
            if operator == '!=' and value != condition_value:
                has_match = True
            if operator == '>=' and value >= condition_value:
                has_match = True
            if operator == '<=' and value <= condition_value:
                has_match = True
            if operator == '>' and value > condition_value:
                has_match = True
            if operator == '<' and value < condition_value:
                has_match = True
        if not has_match:
            return False
    return True


def position_is_possible(conditions, unit):
    """
    If a condition contains a field or position (field + offset + length), check
    if this is even possible given the unit text
    """
    for condition in conditions:
        if not 'field' in condition:
            continue
        has_match = False

        for text_field in unit.unit.get('text_fields', []):
            #fieldname_subfield = condition['field'].split('.')
            if condition['field'] != text_field['name']:
                continue
            #if len(fieldname_subfield) == 1:
                ## 
                ## if condition a subfield (e.g., field.3), see if number in subfield
                ## is lte the number of subfields (text_value['value'])
            #    if int(fieldname_subfield[1]) > len(text_field["value"]  
            #if '.' in condition
                
            if not 'offset' in condition:
                has_match = True
                continue    

            offset = text_field.get('offset', 0)
            first_char = offset + \
                max(text_field.get('unit_start', 0), len(
                    text_field.get('context_before', '')))
            last_char = offset + \
                len(text_field['value']) - text_field.get('unit_end', 0) - 1
            if condition['offset'] >= first_char:
                if condition['offset'] + condition['length'] <= last_char:
                    has_match = True



        other_fields = unit.unit.get('image_fields', []) +  unit.unit.get('markdown_fields', [])
        for field in other_fields:
            if condition['field'] != field['name']:
                has_match = True
             
        if not has_match:
            return False
    return True



def get_condition_value(condition: dict) -> Union[str, float]:
    """
    standardize the condition value to either str or float
    """
    value = condition.get('value')
    if isinstance(value, int) or isinstance(value, float):
        return float(value)
    else:
        return str(value)


def input_is_possible(conditions, item):
    """
    Check whether a condition is possible for an input type item
    """
    item_type = item.get('type', 'text')
    for condition in conditions:
        condition_value = get_condition_value(condition)

        if item_type in ['text', 'textarea', 'email']:
            if not isinstance(condition_value, str):
                return False

        if item_type == 'number':
            if not isinstance(condition_value, float):
                return False
            if 'min' in item and item['min'] < condition_value:
                return False
            if 'max' in item and item['max'] > condition_value:
                return False

    return True
