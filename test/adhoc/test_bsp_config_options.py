#!/usr/bin/env python

"""Tests bsp's -c' and '-C' options

TODO: test error cases ('-c' set to non-existent file; invalid values for
    '--bool-config-value', '--int-config-value', '--float-config-value';
    config conflicts; etc.)
"""

import json
import logging
import os
import subprocess
import tempfile

BSP = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), '../../bin/bsp'))

INPUT = {
    "config": {
        "foo": {
            "a": 111,
            "b": 222,
            "c": 333,
            "d": 444
        }
    },
    "fire_information": []
}

CONFIG_1 = {
    "config": {
        "foo": {
            "b": 2222,
            "c": 3333,
            "d": 4444,
            "bb": "bb"
        },
        "bar": {
            "b": "b"
        },
        "b": "b"
    }
}

CONFIG_2 = {
    "config": {
        "foo": {
            "c": 33333,
            "d": 44444,
            "cc": "cc"
        },
        "baz": {
            "c": "c"
        },
        "c": "c"
    }
}

# Note: "-C foo.d=444444 -C foo.dd=dd -C boo.d=d -C d=d "
#  and "-B dbt=true -B dbf=0 -I di=23 -F df=123.23"
#  and "-C dci=23 -C dcf=123.23"
#  will be specified on the command line

EXPECTED = {
    "config": {
        "foo": {
            "a": 111,
            "b": 2222,
            "c": 33333,
            "d": "444444", # because it was set on command line
            "bb": "bb",
            "cc": "cc",
            "dd": "dd"
        },
        "bar": {
            "b": "b"
        },
        "baz": {
            "c": "c"
        },
        "boo": {
            "d": "d"
        },
        "b": "b",
        "c": "c",
        "d": "d",
        "dbt": True,
        "dbf": False,
        "di": 23,
        "df": 123.23,
        "dci": "23",
        "dcf": "123.23"
    },
    "fire_information": []
}

input_file = tempfile.NamedTemporaryFile()
input_file.write(json.dumps(INPUT))
input_file.flush()

config_1_file = tempfile.NamedTemporaryFile()
config_1_file.write(json.dumps(CONFIG_1))
config_1_file.flush()

config_2_file = tempfile.NamedTemporaryFile()
config_2_file.write(json.dumps(CONFIG_2))
config_2_file.flush()

cmd_args = [
    BSP, '-i', input_file.name,
    '-c', config_1_file.name, '-c', config_2_file.name,
    '-C', 'foo.d=444444', '-C', 'foo.dd=dd',
    '-C', 'boo.d=d', '-C', 'd=d',
    '-B', 'dbt=true', '-B', 'dbf=0',
    '-I', 'di=23', '-F', 'df=123.23',
    '-C', 'dci=23', '-C', 'dcf=123.23'
]
output = subprocess.check_output(cmd_args)
logging.basicConfig(level=logging.INFO)
logging.info("actual:   {}".format(output))
logging.info("expected: {}".format(EXPECTED))
assert EXPECTED == json.loads(output)