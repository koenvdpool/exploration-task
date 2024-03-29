from flask import Flask, Blueprint, render_template, redirect, request, session
from flask_session import Session
import csv


views = Blueprint(__name__, "views")


global itemIDs
itemIDs = []
global rules
rules = []

@views.route("/")
def home():
    # Specify the path to your CSV file
    csv_file_path = "static/totemgame/rules.csv"
    global rules
    global itemIDs
    print("hello")
    # Initialize an empty list to store CSV data
    if not rules:
        #print("initialized")
        rules = []
        itemIDs = []
        # Open the CSV file and read its contents
        with open(csv_file_path, 'r') as csv_file:
            csv_reader = csv.reader(csv_file)
            for row in csv_reader:
                rules.append(row)
                if(row[5] == '1'):
                    itemIDs.append(row[4])
                    
    else:
        rules[10][5] = '1'
        itemIDs = []
        for row in rules:
            if(row[5] == '1'):
                itemIDs.append(row[4])
        
  
    return render_template("index.html",itemIDs = itemIDs)