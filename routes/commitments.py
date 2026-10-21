"""Pohled „Co komu slíbil" – pouze závazky."""
from flask import Blueprint, render_template, request

from models import TaskType
from routes.auth import login_required
from services import task_service
from utils.helpers import ACTIVE_STATUSES

bp = Blueprint("commitments", __name__)


@bp.route("/commitments")
@login_required
def index():
    all_commitments = task_service.filter_tasks(task_service.list_tasks(),
                                                task_type=TaskType.COMMITMENT)
    only_active = request.args.get("all") != "1"
    rows = task_service.filter_tasks(
        all_commitments, search=request.args.get("q", ""),
        statuses=ACTIVE_STATUSES if only_active else (),
    )
    open_count = sum(1 for t in all_commitments if t.status in ACTIVE_STATUSES)
    overdue = [t for t in rows if task_service.is_overdue(t)]
    return render_template("commitments.html", rows=rows, overdue=overdue, open_count=open_count,
                           only_active=only_active, search=request.args.get("q", ""))
