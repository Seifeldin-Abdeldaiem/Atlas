"""The Atlas field models and automatic column mapping.

A dataset is one of two kinds: a task export ("tasks") or a product catalogue
("catalogue"). Each kind has its own field set. A mapping is {field: column
name}; only the kind's required field (`title` or `item_name`) must be set.
Columns that are not mapped are kept unchanged and appear in the export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import AtlasError


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    use: str  # "analysis" | "context" | "display"
    aliases: tuple[str, ...]


# Aliases cover the default export headers of common task tools (Jira, Asana,
# Linear, ClickUp, Monday.com, Trello) plus generic names. Matching ignores
# case, spaces and punctuation. Order within a tuple is preference order.
FIELDS: tuple[Field, ...] = (
    Field("title", "Title", "analysis", ("title", "summary", "taskname", "name", "task", "cardname", "subject", "issuetitle", "itemname", "tasktitle")),
    Field("external_id", "Task ID", "display", ("issuekey", "key", "taskid", "id", "issueid", "cardid", "ticketid", "ticket", "itemid", "identifier", "number")),
    Field("description", "Description", "analysis", ("description", "taskcontent", "carddescription", "notes", "details", "body", "desc", "taskdescription", "content")),
    Field("acceptance_criteria", "Acceptance criteria", "analysis", ("acceptancecriteria", "customfieldacceptancecriteria", "ac", "definitionofdone")),
    Field("project", "Project", "context", ("project", "projectname", "projects", "listname", "board", "boardname", "spacename", "folder", "foldername")),
    Field("team", "Team", "context", ("team", "teamname", "squad", "component", "components", "componentss", "sectioncolumn", "section")),
    Field("department", "Department", "context", ("department", "dept", "businessunit", "division")),
    Field("parent", "Parent task", "context", ("parent", "parentid", "parenttask", "parentissue", "parentkey", "epic", "epiclink", "parentsummary")),
    Field("dependencies", "Dependencies", "context", ("dependencies", "blockedbydependencies", "blockedby", "dependson", "linkedissues", "blocks")),
    Field("status", "Status", "context", ("status", "state", "stage", "column", "progress")),
    Field("priority", "Priority", "display", ("priority", "importance", "severity")),
    Field("assignee", "Assignee", "display", ("assignee", "assignees", "assignedto", "owner", "person", "members")),
    Field("due_date", "Due date", "display", ("duedate", "due", "deadline", "targetdate", "duedatetime")),
    Field("created_at", "Created", "display", ("created", "createdat", "datecreated", "createddate", "creationdate")),
    Field("tags", "Tags", "display", ("tags", "labels", "label", "tag", "keywords")),
)

# Catalogue headers from stock systems, shop platforms and supplier price lists.
# "group" is deliberately not a category alias: in labelled test files it holds
# the answer key, and in real files it is too vague to trust.
CATALOGUE_FIELDS: tuple[Field, ...] = (
    Field("item_name", "Item name", "analysis", ("itemname", "name", "productname", "product", "title", "itemdescription", "productdescription", "description", "desc", "item")),
    Field("details", "More description", "analysis", ("description", "details", "longdescription", "extendeddescription", "notes", "specification", "specs")),
    Field("part_number", "Part number", "analysis", ("partnumber", "partno", "mpn", "manufacturerpartnumber", "manufacturerpartno", "mfrpartno", "pn", "catalognumber", "catalogno", "catno", "modelnumber", "model")),
    Field("brand", "Brand", "analysis", ("brand", "manufacturer", "make", "mfr", "mfg", "brandname", "manufacturername")),
    Field("item_code", "Item code", "display", ("itemcode", "sku", "code", "itemno", "itemnumber", "productcode", "stockcode", "productid", "itemid", "articlenumber", "articleno", "id")),
    Field("category", "Category", "context", ("category", "productcategory", "productgroup", "itemgroup", "subcategory", "class", "family", "producttype")),
    Field("supplier", "Supplier", "display", ("supplier", "vendor", "suppliername", "vendorname")),
    Field("unit", "Unit", "context", ("unit", "uom", "unitofmeasure", "units", "packsize", "pack")),
    Field("stock", "Stock on hand", "display", ("stock", "qty", "quantity", "onhand", "qtyonhand", "quantityonhand", "stocklevel", "instock", "stockqty", "soh", "available")),
    Field("unit_cost", "Unit cost", "display", ("unitcost", "cost", "costprice", "costeach", "buyprice", "purchaseprice", "unitprice", "price")),
    Field("location", "Location", "display", ("location", "bin", "binlocation", "warehouse", "store", "site", "shelf")),
)

KINDS = ("tasks", "catalogue")
FIELD_SETS: dict[str, tuple[Field, ...]] = {"tasks": FIELDS, "catalogue": CATALOGUE_FIELDS}
REQUIRED_FIELD = {"tasks": "title", "catalogue": "item_name"}

FIELDS_BY_KEY = {f.key: f for f in FIELDS}
REQUIRED = ("title",)
_TITLE_SUFFIXES = ("title", "summary", "taskname")
_NAME_SUFFIXES = ("name", "description", "desc")

# Fields that only make sense for one kind; used to guess the kind of a file.
_TASK_SIGNALS = ("project", "team", "department", "parent", "dependencies", "status", "priority", "assignee", "due_date", "acceptance_criteria")
_CATALOGUE_SIGNALS = ("part_number", "brand", "supplier", "unit", "stock", "unit_cost", "location")


def fields_for(kind: str) -> tuple[Field, ...]:
    if kind not in FIELD_SETS:
        raise AtlasError("invalid_kind")
    return FIELD_SETS[kind]


def fields_by_key(kind: str) -> dict[str, Field]:
    return {f.key: f for f in fields_for(kind)}


def norm(name: str) -> str:
    name = name.casefold()
    return re.sub(r"[^0-9a-z]+", "", name)


def _candidates(column: str) -> list[str]:
    """A column matches on its whole name, or on its last segment for
    flattened JSON keys like "fields.summary"."""
    full = norm(column)
    out = [full]
    if "." in column:
        last = norm(column.rsplit(".", 1)[1])
        if last and last != full:
            out.append(last)
    return out


def auto_map(columns: list[str], kind: str = "tasks") -> dict[str, str | None]:
    fields = fields_for(kind)
    required = REQUIRED_FIELD[kind]
    mapping: dict[str, str | None] = {f.key: None for f in fields}
    used: set[str] = set()

    for field in fields:
        best: tuple[int, int, str] | None = None
        for position, column in enumerate(columns):
            if column in used:
                continue
            for candidate in _candidates(column):
                if candidate in field.aliases:
                    rank = (field.aliases.index(candidate), position, column)
                    if best is None or rank < best:
                        best = rank
        if best is not None:
            mapping[field.key] = best[2]
            used.add(best[2])

    if mapping[required] is None:
        suffixes = _TITLE_SUFFIXES if kind == "tasks" else _NAME_SUFFIXES
        for column in columns:
            if column not in used and norm(column).endswith(suffixes):
                mapping[required] = column
                used.add(column)
                break
    return mapping


def detect_kind(columns: list[str]) -> str:
    """Guess whether a file is a task export or a product catalogue from its
    headers. Ties go to tasks, unless only the catalogue finds a name column."""
    as_tasks = auto_map(columns, "tasks")
    as_catalogue = auto_map(columns, "catalogue")
    task_score = sum(1 for key in _TASK_SIGNALS if as_tasks[key])
    catalogue_score = sum(1 for key in _CATALOGUE_SIGNALS if as_catalogue[key])
    if catalogue_score > task_score:
        return "catalogue"
    if catalogue_score == task_score and as_tasks["title"] is None and as_catalogue["item_name"] is not None:
        return "catalogue"
    return "tasks"


def validate_mapping(mapping: dict[str, str | None], columns: list[str], kind: str = "tasks") -> dict[str, str | None]:
    """Check a user-supplied mapping and return it complete (every field present)."""
    by_key = fields_by_key(kind)
    unknown = set(mapping) - set(by_key)
    if unknown:
        raise AtlasError("invalid_mapping", detail=f"unknown field {sorted(unknown)[0]!r}")
    known_columns = set(columns)
    seen: set[str] = set()
    clean: dict[str, str | None] = {key: None for key in by_key}
    for key, column in mapping.items():
        if column in (None, ""):
            continue
        if column not in known_columns:
            raise AtlasError("invalid_mapping", detail="a chosen column isn't in this file")
        if column in seen:
            raise AtlasError("invalid_mapping", detail=f"the column {column!r} is used for two fields")
        seen.add(column)
        clean[key] = column
    return clean
