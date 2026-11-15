from flask import Blueprint, render_template, jsonify, request
import math

bp = Blueprint("nearest_shop", __name__)