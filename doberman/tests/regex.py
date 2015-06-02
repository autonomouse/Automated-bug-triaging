#!/usr/bin/python
import random
import re
import string
import sys

from collections import defaultdict

RANDOM_MAX = 4000

CHARACTERS = string.ascii_letters + string.digits

CATEGORIES = {
    'category_space' : [" ", "\t", "\n"],
    'category_digit': map(chr, range(ord('0'), ord('9')+1)),
    }


def repeat_subnode(node):
    node_value = node[1]
    min_repeat = node_value[0]
    subnode = node_value[2][0]
    instances = [generate_node(subnode) for _ in range(min_repeat)]
    return "".join(instances) 


def generate_subpattern(node):
    subpattern_list = node[1][1]
    return "".join([
        generate_node(subpattern)
        for subpattern in subpattern_list])


def generate_branch(node):
    branches = node[1][1]
    branch = random.choice(branches)
    return generate_match(branch)


def generate_category(node):
    category_name = node[1]
    category_choices = CATEGORIES[category_name]
    return random.choice(category_choices)


type_handlers = {
    'literal': lambda node: chr(node[1]),
    'max_repeat': repeat_subnode,
    'min_repeat': repeat_subnode,
    'any': lambda node: random.choice(CHARACTERS),
    'subpattern': generate_subpattern,
    'branch': generate_branch,
    'in': lambda node: generate_match(node[1]),
    'category': generate_category,
}


def generate_node(node):
    node_type = node[0]
    try:
        handler = type_handlers[node_type]
    except KeyError as exception:
        print("Unknown node: %s" % unicode(node))
        raise exception
    return handler(node)


def generate_match(regex_tree):
    generated_text = ""

    for node in regex_tree:
        node_text = generate_node(node)

        if node_text is None:
            continue

        generated_text += node_text

    return generated_text


def generate_from_regex(regex):
    regex_tree = re.sre_parse.parse(regex).data
    generated_text = generate_match(regex_tree)
    return generated_text
