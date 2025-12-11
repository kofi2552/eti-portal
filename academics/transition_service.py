# academics/transition_service.py
from typing import Dict, List
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.shortcuts import get_object_or_404
from academics.models import (
    Program, Course, ProgramLevel, ProgramCourse, Semester, AcademicYear
)
from users.models import CustomUser as User


def run_program_transition(program_id: int, admin_user) -> Dict:
    """
    Run one program transition (synchronous).
    Returns a result dict with logs and summary.
    - Does NOT touch Enrollment (per spec).
    - Requires: one active AcademicYear and one ready AcademicYear.
    - For the program, determines next level (order +1).
    - For that next level, finds an active semester under the READY academic year.
      Exactly one active semester must exist for that (otherwise fail).
    - Deactivates existing ProgramCourse (is_active=False).
    - Creates new ProgramCourse instances for each base Course -> mapped to next level + the active semester.
    - Updates User.level for students in program (promote), no enrollment changes.
    - Switches academic years: active -> inactive; ready -> active (and ready=False).
    """

    logs: List[str] = []
    created_count = 0
    deactivated_count = 0
    promoted_count = 0

    program = get_object_or_404(Program, id=program_id)

    # Validate academic years
    active_year = AcademicYear.objects.filter(is_active=True).first()
    ready_year = AcademicYear.objects.filter(is_ready=True).first()

    if not active_year:
        raise ValidationError("No active academic year found. Please set an active academic year before transition.")
    if not ready_year:
        raise ValidationError("No academic year marked as ready. Please prepare the next academic year and mark it ready.")
    if active_year.id == ready_year.id:
        raise ValidationError("Active academic year cannot be the same as the ready academic year.")

    logs.append(f"[{timezone.now().isoformat()}] Active year: {active_year.name}; Ready year: {ready_year.name}")

    # Program levels mapping
    levels = list(program.levels.order_by("order"))
    if not levels:
        raise ValidationError("No ProgramLevel entries defined for this program.")

    level_map = {lvl.order: lvl for lvl in levels}

    # Determine next level(s) that students will move into
    # Here we assume that transition moves students from order X => X+1.
    # We'll create ProgramCourse instances for the next level only (order = current_order +1).
    # But we must ensure that the next level exists (we validate that below).
    # For simplicity, we will pick the "next level" as the one with order = 2 (i.e. students will move from 1->2).
    # A safer approach is to consider all students' current levels and compute next levels per group.
    # The following pre-check ensures every student currently in this program has a valid next level.
    # Gather students of the program (based on their user.level.program relation)
    students_qs = User.objects.filter(role="student", level__program=program).select_related("level")
    student_count = students_qs.count()
    logs.append(f"[INFO] Found {student_count} students associated with program '{program.name}' (via user.level).")

    # Pre-check: for all distinct current levels among these students, ensure there is a next level and an active semester under ready_year
    distinct_levels = sorted({stu.level.order for stu in students_qs if stu.level is not None})
    if not distinct_levels:
        logs.append("[INFO] No student-level associations found; transition will still create ProgramCourse instances for next level order=2 if present.")

    next_levels_required = set()
    for cur_order in distinct_levels:
        next_order = cur_order + 1
        next_lvl = level_map.get(next_order)
        if not next_lvl:
            raise ValidationError(f"Next level (order {next_order}) not found for program {program.name}. Aborting transition.")
        # Check exactly one active semester under this next level in the ready year
        sem_qs = Semester.objects.filter(level=next_lvl, academic_year=ready_year, is_active=True)
        if sem_qs.count() == 0:
            raise ValidationError(
                f"No active semester found under level '{next_lvl.level_name}' for academic year '{ready_year.name}'. "
                "Please create and mark one semester active under that level in the ready academic year."
            )
        if sem_qs.count() > 1:
            raise ValidationError(
                f"Multiple active semesters found under level '{next_lvl.level_name}' for academic year '{ready_year.name}'. "
                "Only one active semester is permitted per level."
            )
        next_levels_required.add(next_lvl.id)
        logs.append(f"[CHECK] Next level order={next_order} validated with active semester '{sem_qs.first().name}'.")

    # If no student levels were found, fallback: use level order 2 (common case transitioning 1->2)
    if not next_levels_required:
        fallback_next = level_map.get(2)
        if not fallback_next:
            raise ValidationError("Could not determine next level (no students found and program has no order=2 level).")
        sem_qs = Semester.objects.filter(level=fallback_next, academic_year=ready_year, is_active=True)
        if sem_qs.count() != 1:
            raise ValidationError("For fallback next level, there must be exactly one active semester under ready academic year.")
        next_levels_required.add(fallback_next.id)
        logs.append(f"[FALLBACK] No student levels found; using level {fallback_next.level_name} as next level.")

    # Make a mapping level_id -> active semester (single entry)
    level_to_active_semester = {}
    for lvl_id in next_levels_required:
        lvl = ProgramLevel.objects.get(id=lvl_id)
        sem = Semester.objects.get(level=lvl, academic_year=ready_year, is_active=True)
        level_to_active_semester[lvl_id] = sem
        logs.append(f"[MAP] Level '{lvl.level_name}' -> semester '{sem.name}' (ready year).")

    # Begin atomic transition
    with transaction.atomic():
        # 1) Deactivate all existing ProgramCourse instances for this program
        active_pcs = ProgramCourse.objects.filter(program=program, is_active=True)
        deactivated_count = active_pcs.count()
        if deactivated_count:
            active_pcs.update(is_active=False)
            logs.append(f"[STEP] Deactivated {deactivated_count} existing ProgramCourse(s) for program '{program.name}'.")
        else:
            logs.append("[STEP] No active ProgramCourse instances to deactivate.")

        # 2) Create new ProgramCourse instances for each base Course but only for the required next levels
        base_courses = Course.objects.filter(program=program)
        logs.append(f"[STEP] Creating new ProgramCourse instances from {base_courses.count()} base Course(s).")

        for base in base_courses:
            # For each required next level, create a ProgramCourse using that level's active semester
            for lvl_id, sem in level_to_active_semester.items():
                lvl = ProgramLevel.objects.get(id=lvl_id)
                # Avoid duplicates
                exists = ProgramCourse.objects.filter(
                    program=program, level=lvl, semester=sem, title=base.title
                ).exists()
                if exists:
                    logs.append(f"[SKIP] ProgramCourse for '{base.title}' @ {lvl.level_name} ({sem.name}) already exists.")
                    continue

                pc = ProgramCourse.objects.create(
                    base_course=base,
                    program=program,
                    level=lvl,
                    semester=sem,
                    title=base.title,
                    credit_hours=base.credit_hours,
                    course_code=ProgramCourse.generate_code_for(base.title, lvl),
                    is_active=True
                )
                created_count += 1
                logs.append(f"[CREATE] ProgramCourse '{pc.title}' ({pc.course_code}) created for level {lvl.level_name} and semester {sem.name}.")

        # 3) Promote students to next level (update user.level only)
        # For each student in the program, compute next level and update user.level (no enrollment)
        promoted_count = 0
        for stu in students_qs:
            cur_lvl = stu.level
            if not cur_lvl:
                # ignore or fail? previous validation would have caught missing levels for students
                continue
            next_lvl = level_map.get(cur_lvl.order + 1)
            if not next_lvl:
                # no next level - skip (should not happen due to earlier checks)
                continue
            stu.level = next_lvl
            stu.save(update_fields=["level"])
            promoted_count += 1
            logs.append(f"[PROMOTE] Student {stu.get_full_name()} promoted to {next_lvl.level_name}.")

        # 4) Switch academic years
        active_year.is_active = False
        active_year.save(update_fields=["is_active"])

        ready_year.is_active = True
        ready_year.is_ready = False
        ready_year.save(update_fields=["is_active", "is_ready"])

        logs.append(f"[FINAL] Academic years flipped: '{active_year.name}' -> inactive; '{ready_year.name}' -> active (ready cleared).")

    result = {
        "success": True,
        "timestamp": timezone.now().isoformat(),
        "logs": logs,
        "created_count": created_count,
        "deactivated_count": deactivated_count,
        "promoted_count": promoted_count,
    }
    return result
