"""预演行谓词：成绩表 exploration_space=E-rehearsal 的行不计入正式成绩。"""

REHEARSAL_CELL = "E-rehearsal"
REHEARSAL_SCORE_COL = "rehearsal_score"


def is_rehearsal_row(row: dict) -> bool:
    return str(row.get("exploration_space") or "").strip() == REHEARSAL_CELL
