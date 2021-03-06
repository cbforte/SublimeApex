import sublime
import os
import sys
import json
import csv
import urllib
import pprint
import sys
import time
import base64
import zipfile
import shutil
import xml.dom.minidom
 
from .salesforce import message
from .salesforce import xmltodict
from . import context
from xml.sax.saxutils import unescape

def get_view_by_id(view_id):
    """
    Get the view in the active window by the view_id

    @view_id: id of view
    @return: view
    """

    view = None
    for v in sublime.active_window().views():
        if v.id() == view_id:
            view = v

    return view

def base64_zip(zipfile):
    with open(zipfile, "rb") as f:
        bytes = f.read()
        base64String = base64.b64encode(bytes)

    return base64String.decode('UTF-8')

def extract_zip(base64String, outputdir):
    """
    1. Decode base64String to zip
    2. Extract zip to files
    """

    # Decode base64String to zip
    if not os.path.exists(outputdir): os.makedirs(outputdir)
    zipdir = outputdir + "/package.zip"
    with open(zipdir, "wb") as fout:
        fout.write(base64.b64decode(base64String))
        fout.close()

    # Unzip sobjects.zip to file
    f = zipfile.ZipFile(zipdir, 'r')
    for fileinfo in f.infolist():
        path = outputdir
        directories = fileinfo.filename.split('/')
        for directory in directories:
            # replace / to &, because there has problem in open method
            try:
                quoted_dir = urllib.parse.unquote(directory).replace("/", "&")
            except:
                quoted_dir = urllib.unquote(directory).replace("/", "&")
            path = os.path.join(path, quoted_dir)
            if directory == directories[-1]: break # the file
            if not os.path.exists(path):
                os.makedirs(path)

        outputfile = open(path, "wb")
        shutil.copyfileobj(f.open(fileinfo.filename), outputfile)
        outputfile.close()

    # Close zipFile opener
    f.close()

def format_debug_logs(toolingapi_settings, records):
    if len(records) == 0: return "No available logs."

    # Get debug_log_headers and debug_log_headers_properties
    debug_log_headers = toolingapi_settings["debug_log_headers"]
    debug_log_headers_properties = toolingapi_settings["debug_log_headers_properties"]

    # Headers
    headers = ""
    for header in debug_log_headers:
        headers += "%-*s" % (debug_log_headers_properties[header]["width"], 
            debug_log_headers_properties[header]["label"])

    # Content
    content = ""
    records = reversed(sorted(records, key=lambda k : k['StartTime']))
    for record in records:
        for header in debug_log_headers:
            if header == "StartTime":
                content += "%-*s" % (debug_log_headers_properties[header]["width"],
                    record[header][0:19].replace('T', ' '))
                continue
            content += "%-*s" % (debug_log_headers_properties[header]["width"], record[header])
        content += "\n"

    return headers + "\n" + content[:len(content)-1]

def format_error_message(result):
    """
    Format message as below format
           message:     The requested resource does not exist   
               url:     url
         errorCode:     NOT_FOUND                       
       status_code:     404     

    @result: dict error when request status code > 399
    @return: formated error message   
    """

    error_message = ""
    for key in result:
        error_message += "% 20s\t" % "{0}: ".format(key)
        error_message += "%-30s\t" % none_value(result[key]) + "\n"

    return error_message[:len(error_message)-1]

def format_waiting_message(result, header=""):
    error_message = header + "\n" + "-" * 150 + "\n"
    for key in result:
        if isinstance(result[key], list): continue
        error_message += "% 30s\t" % "{0}: ".format(key)
        error_message += "%-30s\t" % none_value(result[key]) + "\n"

    if "messages" in result:
        messages = result["messages"]
        error_message += message.SEPRATE.format("Deploy Messages")
        for key in messages[0].keys():
            error_message += "%-30s" % key.capitalize()
        error_message += "\n"
        for msg in messages:
            for key in msg:
                error_message += "%-30s" % none_value(msg[key])
            error_message += "\n"

    return error_message

def none_value(value):
    """
    If value is None, return "", if not, return value

    @value: value
    """

    if value == None: return ""
    return value
    
def is_python3x():
    """
    If python version is 3.x, return True
    """

    return sys.version > '3'

"""
Below three functions are used to parse completions out of box.
"""
def parse_method(classname, methods):
    methods_dict = {}
    for method in methods:
        if not method["parameters"]:
            methods_dict[method["name"] + "()\t" + method["returnType"]] = method["name"] + "()$0"
        else:
            parameters = ''
            for parameter in method["parameters"]:
                parameters += parameter["type"] + " " + parameter["name"] + ", "
            parameters = parameters[ : -2]
            methods_dict[method["name"] + "(" + parameters + ")\t" +\
                method["returnType"]] = method["name"] + "($1)$0"

    return methods_dict

def parse_properties(classname, properties):
    if not properties: return {}
    properties_dict = {}
    for property in properties:
        properties_dict[property["name"]] = property["name"] + "$0"

    return properties_dict

def parse_constructors(classname, constructors):
    if not constructors: return {}
    constructors_dict = {}
    for constructor in constructors:
        if constructor["name"] == None: continue
        if not constructor["parameters"]:
            constructors_dict[constructor["name"] + "()"] = constructor["name"] + "()$0"
        else:
            parameters = ''
            for parameter in constructor["parameters"]:
                parameters += parameter["type"] + " " + parameter["name"] + ", "
            parameters = parameters[ : -2]
            constructors_dict[constructor["name"] + "(" + parameters + ")"] = constructor["name"] + "($0)"

def parse_all(apex):
    """
    Usage:
        from .salesforce import util
        import json
        apex_json = util.parse_all(apex)
        json.dump(apex_json, open("c:/text.json",'w'))

    """

    apex_completions = {}
    for namespace in apex.keys():
        for class_name in apex[namespace]:
            class_detail = apex[namespace][class_name]

            constructors_dict = parse_constructors(class_name, class_detail["constructors"])
            methods_dict = parse_method(class_name, class_detail["methods"])
            properties_dict = parse_properties(class_name, class_detail["properties"])
            # all_dict = dict(list(methods_dict.items()) + list(properties_dict.items()))

            # Parse constructor, methods and properties
            apex_completions[class_name.lower()] = {}
            apex_completions[class_name.lower()]["constructors"] = constructors_dict
            apex_completions[class_name.lower()]["methods"] = methods_dict
            apex_completions[class_name.lower()]["properties"] = properties_dict

            # Class Name Full Name Attribute
            apex_completions[class_name.lower()]["name"] = class_name
            
    return apex_completions

def parse_test_result(test_result):
    """
    format test result as specified format

    @result: Run Test Request result
    @return: formated string
    """

    # Parse Test Result
    if len(test_result) == 0: return "It's not test class"
    separate = "-" * 100
    test_result_desc = ' Test Result\n'
    test_result_content = ""
    for record in test_result:
        test_result_content += separate + "\n"
        test_result_content += "% 30s    " % "MethodName: "
        test_result_content += "%-30s" % none_value(record["MethodName"]) + "\n"
        test_result_content += "% 30s    " % "TestTimestamp: "
        test_result_content += "%-30s" % none_value(record["TestTimestamp"]) + "\n"
        test_result_content += "% 30s    " % "ApexClass: "
        class_name = record["ApexClass"]["Name"]
        test_result_content += "%-30s" % class_name + "\n"
        test_result_content += "% 30s    " % "Pass/Fail: "
        test_result_content += "%-30s" % none_value(record["Outcome"]) + "\n"
        test_result_content += "% 30s    " % "Error Message: "
        test_result_content += "%-30s" % none_value(record["Message"]) + "\n"
        test_result_content += "% 30s    " % "Stack Trace: "
        test_result_content += "%-30s" % none_value(record["StackTrace"]) + "\n"

    return_result = class_name + test_result_desc + test_result_content + "\n"

    # Parse Debug Log Part
    debug_log_desc = separate + "\nYou can choose LogId and view it in SFDC\n" + separate + "\n"
    debug_log_content = "LogId: "
    if len(test_result) > 0 and test_result[0]["ApexLogId"] != None:
        debug_log_content += test_result[0]["ApexLogId"]

    return_result += debug_log_desc + debug_log_content

    return return_result

def parse_validation_rule(toolingapi_settings, sobjects):
    """
    Parse the validation rule in Sobject.object to csv

    @toolingapi_settings: toolingapi.sublime-settings reference
    @sobject: sobject name
    @validation_rule_path: downloaded objects path by Force.com IDE or ANT
    """

    # Open target file
    outputdir = toolingapi_settings["workspace"] + "/describe/validation rules"
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)

    # Create or Edit csv File
    if is_python3x():
        fp_validationrules = open(outputdir + "/validation rules.csv", "a", newline='')
    else:
        fp_validationrules = open(outputdir + "/validation rules.csv", "ab")

    # Initiate CSV Writer and Write headers
    columns = toolingapi_settings["validation_rule_columns"]
    dict_write = csv.DictWriter(fp_validationrules, columns)
    dict_write.writer.writerow([v.capitalize() for v in columns])

    # Open workflow source file
    validation_rule_path = toolingapi_settings["workspace"] + "/metadata/unpackaged/objects"
    for sobject in sobjects:
        try:
            fp = open(validation_rule_path + "/" + sobject + ".object", "rb")
        except IOError:
            # If one sobject is not exist, We don't need do anything
            continue

        result = xmltodict.parse(fp.read())
        fp.close()
        
        ######################################
        # Rules Part
        ######################################
        try:
            rules = result["CustomObject"]["validationRules"]
            write_metadata_to_csv(dict_write, columns, rules, sobject)
        except KeyError:
            # If one sobject doesn't have vr, We don't need do anything
            pass

    # Close fp
    fp_validationrules.close()

def parse_workflow_metadata(toolingapi_settings, sobject):
    """
    Parse Sobject.workflow to csv, including rule, field update and alerts

    @toolingapi_settings: toolingapi.sublime-settings reference
    @sobject: sobject name
    @workflow_metadata_path: downloaded workflow path by Force.com IDE or ANT
    """
    # Open workflow source file
    workflow_metadata_path = toolingapi_settings["workspace"] + "/metadata/unpackaged/workflows"
    try:
        fp = open(workflow_metadata_path + "/" + sobject + ".workflow", "rb")
    except IOError:
        return

    # Outputdir for save workflow rule, field update, email alert
    # and outbound message and task
    outputdir = toolingapi_settings["workspace"] + "/describe/workflows"
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)

    # Convert xml to dict
    result = xmltodict.parse(fp.read())
    fp.close()

    ######################################
    # Rules Part
    ######################################
    try:
        rules = result["Workflow"]["rules"]
    except KeyError:
        return

    # Initiate CSV Writer and Write headers
    columns = toolingapi_settings["workflow_rule_columns"]
    try:
        # Python 3.x
        fp = open(outputdir + "/" + sobject + " workflow rule.csv", "wt", newline='')
    except:
        # Python 2.x
        fp = open(outputdir + "/" + sobject + " workflow rule.csv", "wb")
    dict_write = csv.DictWriter(fp, columns, dialect=csv.excel)
    dict_write.writer.writerow([v.capitalize() for v in columns])

    # Write rows
    write_metadata_to_csv(dict_write, columns, rules, sobject)

    # Close fp
    fp.close()

    ######################################
    # Field Update Part
    ######################################
    try:
        fieldUpdates = result["Workflow"]["fieldUpdates"]
    except KeyError:
        return

    # Initiate CSV Writer and Write headers
    columns = toolingapi_settings["workflow_field_update_columns"]
    try:
        # Python 3.x
        fp = open(outputdir + "/" + sobject + " workflow field update.csv", "wt", newline='')
    except:
        # Python 2.x
        fp = open(outputdir + "/" + sobject + " workflow field update.csv", "wb")
    dict_write = csv.DictWriter(fp, columns)
    dict_write.writer.writerow([v.capitalize() for v in columns])

    # Write rows
    write_metadata_to_csv(dict_write, columns, fieldUpdates, sobject)

    # Close fp
    fp.close()

    ######################################
    # Email Alert Part
    ######################################
    try:
        alerts = result["Workflow"]["alerts"]
    except KeyError:
        return

    # Initiate CSV Writer and Write headers
    columns = toolingapi_settings["workflow_email_alert_columns"]
    try:
        # Python 3.x
        fp = open(outputdir + "/" + sobject + " email alert.csv", "wt", newline='')
    except:
        # Python 2.x
        fp = open(outputdir + "/" + sobject + " email alert.csv", "wb")
    dict_write = csv.DictWriter(fp, columns)
    dict_write.writer.writerow([v.capitalize() for v in columns])

    # Write rows
    write_metadata_to_csv(dict_write, columns, alerts, sobject)

    # Close fp
    fp.close()

    ######################################
    # Outbound Message Part
    ######################################
    try:
        outboundMessages = result["Workflow"]["outboundMessages"]
    except KeyError:
        return

    # Initiate CSV Writer and Write headers
    columns = toolingapi_settings["workflow_outbound_message_columns"]
    try:
        # Python 3.x
        fp = open(outputdir + "/" + sobject + " outbound message.csv", "wt", newline='')
    except:
        # Python 2.x
        fp = open(outputdir + "/" + sobject + " outbound message.csv", "wb")
    dict_write = csv.DictWriter(fp, columns)
    dict_write.writer.writerow([v.capitalize() for v in columns])

    # Write rows
    write_metadata_to_csv(dict_write, columns, outboundMessages, sobject)

    # Close fp
    fp.close()

    ######################################
    # Task Part
    ######################################
    try:
        tasks = result["Workflow"]["tasks"]
    except KeyError:
        return

    # Initiate CSV Writer and Write headers
    columns = toolingapi_settings["workflow_task_columns"]
    try:
        # Python 3.x
        fp = open(outputdir + "/" + sobject + " task.csv", "wt", newline='')
    except:
        # Python 2.x
        fp = open(outputdir + "/" + sobject + " task.csv", "wb")
    dict_write = csv.DictWriter(fp, columns)
    dict_write.writer.writerow([v.capitalize() for v in columns])

    # Write rows
    write_metadata_to_csv(dict_write, columns, tasks, sobject)

    # Close fp
    fp.close()

def write_metadata_to_csv(dict_write, columns, metadata, sobject):
    """
    this method is invoked by function in this module

    @fp: output csv file open reference
    @columns: your specified metadata workbook columns in settings file
    @metadata: metadata describe
    """

    # If sobject has only one rule, it will be dict
    # so we need to convert it to list
    if isinstance(metadata, dict):
        metadata_temp = [metadata]
        metadata = metadata_temp

    # We just use sobject as column, 
    # it's value is assigned with sobject parameter
    columns = [col for col in columns if col != "sobject"]

    for rule in metadata:
        row_value = [sobject]
        for key in columns:
            # Because Workflow rule criteria has different type
            # If key is not in rule, just append ""
            if key not in rule.keys():
                row_value.append("")
                continue

            cell_value = rule[key]
            if isinstance(cell_value, list):
                value = ''
                if len(cell_value) > 0:
                    if isinstance(cell_value[0], dict):
                        values = []
                        for cell_dict in cell_value:
                            for cell_dict_key in cell_dict.keys():
                                values.append(cell_dict[cell_dict_key])
                            value += " ".join(values) + "\n"
                    else:
                        value = " ".join(cell_value) + "\n"

                    cell_value = value[ : -1]
                else:
                    cell_value = ""

            elif isinstance(cell_value, dict):
                value = ''
                for cell_key in cell_value.keys():
                    if cell_value[cell_key] == None:
                        value += cell_key + ": ' '" + "\n"
                    else:
                        value += cell_key + ": " + cell_value[cell_key] + "\n"

                cell_value = value[ : -1]

            elif cell_value == None:
                cell_value = ""

            else:
                cell_value = "%s" % cell_value

            # Unescape special code to normal
            try:
                # Python 3.x
                cell_value = urllib.parse.unquote(unescape(cell_value, 
                    {"&apos;": "'", "&quot;": '"'}))
            except:
                # Python 2.x
                cell_value = urllib.unquote(unescape(cell_value, 
                    {"&apos;": "'", "&quot;": '"'}))

            # Append cell_value to list in order to write list to csv
            if is_python3x():
                row_value.append(cell_value)
            else:
                row_value.append(cell_value.encode("utf-8"))

        # Write row
        dict_write.writer.writerow(row_value)

NOT_INCLUDED_COLUMNS = ["urls", "attributes"]
def list2csv(fp, records):
    """
    convert simple dict in list to csv

    @records: [{"1": 1}, {"2": 2}]
    """
    # If records size is 0, just return
    if len(records) == 0: return "No Custom Fields"
    
    writer = csv.DictWriter(fp, [k.capitalize() for k in records[0] if k not in NOT_INCLUDED_COLUMNS])
    writer.writeheader()
    for record in records:
        writer.writerow(dict((k.capitalize(), v) for k, v in record.items() if k not in NOT_INCLUDED_COLUMNS))

    # Release fp
    fp.close()

def parse_describe_layout_result(fp, result):
    """
    parse layout describe result, 
    three part: 
        1. Edit Layouts, 
        2. View Layouts
        3. Available Picklist Value

    up to now, only the Available Picklist Value part is available

    @result: page layout describe result of specified record type
    """
    #########################################
    # Available Picklist Values for recordtype
    #########################################
    try:
        picklistsForRecordType = result["recordTypeMappings"]["picklistsForRecordType"]
    except KeyError:
        fp.write("No available picklist field.")
        fp.close()
        return
    
    headers = ["Picklist Field", "Available Values"]
    dict_write = csv.DictWriter(fp, headers, quoting=csv.QUOTE_ALL)

    # Write headers
    dict_write.writer.writerow(headers)

    # Write body
    for picklist in picklistsForRecordType:
        field_name = picklist["picklistName"]
        picklistValues = picklist["picklistValues"]

        values = []
        if isinstance(picklistValues, dict):
            values.append(picklistValues["value"])
        elif isinstance(picklistValues, list):
            values = [p["value"] for p in picklistValues]

        if not is_python3x():
            values = [v.encode("utf-8") for v in values]

        value = "\n".join(values)

        # Write row
        dict_write.writer.writerow([field_name, value])

    # Close fp
    fp.close()

def parse_execute_anonymous_xml(result):
    """
    Get the compile result in the xml result

    @result: execute anonymous result, it's a xml

    @return: formated string
    """

    compiled = result["compiled"]
    debugLog = result["debugLog"]

    view_result = ''
    if compiled == "true":
        view_result = debugLog
    elif compiled == "false":
        line = result["line"]
        column = result["column"]
        compileProblem = result["compileProblem"]
        view_result = compileProblem + " at line " + line +\
            " column " + column + "\n" + "-" * 100 + "\n" + debugLog

    if is_python3x():
        view_result = urllib.parse.unquote(unescape(view_result, 
            {"&apos;": "'", "&quot;": '"'}))
    else:
        view_result = urllib.unquote(unescape(view_result, 
            {"&apos;": "'", "&quot;": '"'}))

    return view_result

def generate_workbook(result, workspace, workbook_field_describe_columns):
    """
    generate workbook for sobject according to user customized columns
    you can change the workbook_field_describe_columns in default settings

    @result: sobject describe result
    @workspace: your specified workspace in toolingapi.sublime-settings
    @workflow_field_update_columns: your specified workbook columns in toolingapi.sublime-settings
    """
    # Get sobject name
    sobject = result.get("name")

    # Get fields
    fields = result.get("fields")
    fields_key = workbook_field_describe_columns

    # If workbook path is not exist, just make it
    outputdir = workspace + "/describe/sobject workbooks"
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)

    # Create new csv file for this workbook
    # fp = open(outputdir + "/" + sobject + ".csv", "wb", newline='')
    if is_python3x():
        fp = open(outputdir + "/" + sobject + ".csv", "w", newline='')
    else:
        fp = open(outputdir + "/" + sobject + ".csv", "wb")
    
    #------------------------------------------------------------
    # Headers, all headers are capitalized
    #------------------------------------------------------------
    headers = [column.capitalize() for column in fields_key]
    dict_write = csv.DictWriter(fp, headers, quoting=csv.QUOTE_ALL)
    dict_write.writer.writerow(headers)

    #------------------------------------------------------------
    # Fields Part (All rows are sorted by field label)
    #------------------------------------------------------------
    fields = sorted(fields, key=lambda k : k['label'])
    for field in fields:
        row = []
        for key in fields_key:
            # Get field value by field API(key)
            row_value = field.get(key)
            
            if isinstance(row_value, list):
                if key == "picklistValues":
                    value = ''
                    if len(row_value) > 0:
                        for item in row_value:
                            value += item.get("value") + "\n"
                        row_value = value
                    else:
                        row_value = ""
                elif key == "referenceTo":
                    if len(row_value) > 0:
                        row_value = row_value[0]
                    else:
                        row_value = ""
            elif row_value == None:
                row_value = ""
            else:
                row_value = "%s" % row_value

            if  is_python3x():
                row.append(row_value)
            else:
                row.append(row_value.encode('utf-8'))

        # Write row to csv
        dict_write.writer.writerow(row)

    # Close fp
    fp.close()

    # Display Success Message
    sublime.set_timeout(lambda:sublime.status_message(sobject + " workbook is generated"), 10)

    # Return outputdir
    return outputdir

seprate = 100 * "-" + "\n"
def parse_execute_query_result(result):
    """
    Parse the soql query result to formated string

    @result: soql query result, it's a dict

    @return: formated string
    """

    def parse_records(value, view_result):
        #------------------------------------------------------------
        # Part of TotalSize, Title and seprate line
        #------------------------------------------------------------
        # Get the field list of record and remove attributes
        records = value["records"]
        record_keys = records[0].keys()
        record_keys = [ele for ele in record_keys if ele != "attributes"]

        # Append columns part into view_result
        columns = ""
        for key in record_keys:
            columns += "%-30s" % key

        view_result += records[0]["attributes"]["type"] + " totalSize: \t" +\
            str(value.get("totalSize")) + "\n"
        view_result += seprate
        view_result += columns + "\n" + len(columns) * "-" + "\n"

        #------------------------------------------------------------
        # Part of Field Value
        #------------------------------------------------------------
        for record in value.get("records"):
            row = ""
            for key in record_keys:
                # Get field value by field API
                row_value = record.get(key)
                if row_value == None:
                    row_value = ""

                if isinstance(row_value, dict):
                    row_value = str(len(row_value["records"]))
                else:
                    row_value = "%-30s" % row_value
                row += row_value
            view_result += row + "\n"
            
        return view_result

    # If no query result, just...
    if "totalSize" in result and result.get("totalSize") == 0:
        return "No query result."

    parent_view_result = ""
    parent_view_result = parse_records(result, parent_view_result)

    child_view_result = ""
    for parent_record in result["records"]:
        for key in parent_record.keys():
            if key == "attributes":
                continue

            value = parent_record[key]
            if isinstance(value, dict) and value != None:
                child_view_result = parse_records(value, child_view_result)
                child_view_result += "\n"

    return parent_view_result + child_view_result

record_keys = ["label", "name", "type", "length"]
record_key_width = {
    "label": 40, 
    "name": 40, 
    "type": 15, 
    "length": 2
}
recordtype_key_width = {
    "available": 10,
    "recordTypeId": 20,
    "name": 35,
    "defaultRecordTypeMapping": 15
}
childrelationship_key_width = {
    "field": 35,
    "relationshipName": 35,
    "childSObject": 30,
    "cascadeDelete": 12
}

def parse_sobject_field_result(result):
    """
    According to sobject describe result, display recordtype information, child sobjects 
    information and the field information.

    @result: sobject describe information, it's a dict

    @return: formated string including the three parts
    """

    # Get sobject name
    sobject = result.get("name")

    # View Name or Header
    view_result = sobject + " Describe:\n"

    #------------------------------------------------
    # Record Type Part
    #------------------------------------------------
    recordtypes = result.get("recordTypeInfos")
    pprint.pprint(recordtypes)
    view_result += seprate
    view_result += "Record Type Info: \t" + str(len(recordtypes)) + "\n"
    view_result += seprate

    # Get Record Type Info Columns
    recordtype_keys = []
    if len(recordtypes) > 0:
        recordtype_keys = recordtypes[0].keys()

    columns = ""
    for key in recordtype_keys:
        if not key in recordtype_key_width: continue
        key_width = recordtype_key_width[key]
        if key == "defaultRecordTypeMapping": key = "default"
        columns += "%-*s" % (key_width, key.capitalize())

    view_result += columns + "\n"
    view_result += len(columns) * "-" + "\n"

    for recordtype in recordtypes:
        row = ""
        for key in recordtype_keys:
            if key not in recordtype_key_width: continue
            
            # Get field value by field API
            # and convert it to str
            row_value = recordtype.get(key)
            if row_value == None:
                row_value = ""

            key_width = recordtype_key_width[key]
            row_value = "%-*s" % (key_width, row_value)
            row += row_value
            
        view_result += row + "\n"

    view_result += "\n"

    #------------------------------------------------
    # Child Relationship
    #------------------------------------------------
    childRelationships = result.get("childRelationships")
    view_result += seprate
    view_result += "ChildRelationships Info: \t" + str(len(childRelationships)) + "\n"
    view_result += seprate

    # Get Record Type Info Columns
    childRelationships_keys = childrelationship_key_width.keys()
    columns = ""
    for key in childRelationships_keys:
        columns += "%-*s" % (30, key.capitalize())

    view_result += columns + "\n"
    view_result += len(columns) * "-" + "\n"

    for childRelationship in childRelationships:
        row = ""
        for key in childRelationships_keys:
            # Get field value by field API
            # and convert it to str
            row_value = childRelationship.get(key)
            if row_value == None:
                row_value = ""

            row_value = "%-*s" % (30, row_value)
            row += row_value
            
        view_result += row + "\n"

    view_result += "\n"

    #------------------------------------------------
    # Fields Part
    #------------------------------------------------
    # Output totalSize Part
    fields = result.get("fields")
    view_result += seprate
    view_result += "Total Fields: \t" + str(len(fields)) + "\n"
    view_result += seprate

    # Ouput Title and seprate line
    columns = ""
    for key in record_keys:
        key_width = record_key_width[key]
        columns += "%-*s" % (key_width, key.capitalize())

    view_result += columns + "\n"
    view_result += len(columns) * "-" + "\n"

    # Sort fields list by lable of every field
    fields = sorted(fields, key=lambda k : k['label'])

    # Output field values
    for record in fields:
        row = ""
        for key in record_keys:
            row_value = record.get(key)
            if row_value == None:
                row_value = ""

            key_width = record_key_width[key]
            row_value = "%-*s" % (key_width, row_value)
            row += row_value

        view_result += row + "\n"

    return view_result
    
def getUniqueElementValueFromXmlString(xmlString, elementName):
    """
    Extracts an element value from an XML string.
    
    For example, invoking 
    getUniqueElementValueFromXmlString('<?xml version="1.0" encoding="UTF-8"?><foo>bar</foo>', 'foo')
    should return the value 'bar'.
    """
    xmlStringAsDom = xml.dom.minidom.parseString(xmlString)
    elementsByName = xmlStringAsDom.getElementsByTagName(elementName)
    elementValue = None
    if len(elementsByName) > 0:
        elementValue = elementsByName[0].toxml().replace('<' + elementName + '>','').replace('</' + elementName + '>','')
    return elementValue

def get_file_attr(file_name):
    try:
        folder, extension = os.path.splitext(file_name)
        name = ""
        if "\\" in folder:
            name = folder[folder.rfind("\\")+1:]
        elif "/" in folder:
            name = folder[folder.rfind("/")+1:]
        return name, extension
    except:
        pass

def get_component_attribute(file_name):
    """
    get the component name by file_name, and then get the component_url and component_id
    by component name and local settings

    @file_name: local component full file name, for example:
    D:\ForcedotcomWorkspace\pro-exercise-20130625\ApexClass\AccountChartController.cls

    @return: for example, component_attribute = {
        "body": "Body",
        "extension": ".cls",
        "id": "01pO00000009isEIAQ",
        "is_test": false,
        "type": "ApexClass",
        "url": "/services/data/v28.0/sobjects/ApexClass/01pO00000009isEIAQ"
    }
    """
    # Get toolingapi settings
    toolingapi_settings = context.get_toolingapi_settings()

    # Get component type
    name, extension = get_file_attr(file_name)

    # If extension is None, just return
    if extension == None or extension not in toolingapi_settings["component_extensions"]:
        return

    component_type = toolingapi_settings[extension]
    username = toolingapi_settings["username"]
    component_settings = sublime.load_settings(context.COMPONENT_METADATA_SETTINGS)

    try:
        component_attribute = component_settings.get(username)[component_type][name]
    except:
        return (None, None)

    # Return tuple
    return (component_attribute, name)