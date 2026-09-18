import logging

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.schemas import OptimizeRequest, OptimizeResponse, DirectiveInterpretation
from app.optimizer import solve_schedule
from app.validator import validate_final_schedule, validate_totals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gridwise")

app = FastAPI(title="GridWise Energy Optimizer")


def interpret_notes(operator_notes: list[str]) -> list[dict]:
    """Stub — Person A's LLM interpreter will replace this. Returns no_op for every note."""
    return [
        {
            "note_index": i,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "stub: LLM interpreter not yet wired in",
        }
        for i in range(len(operator_notes))
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_energy(request: OptimizeRequest):
    try:
        hours_data = [h.model_dump() for h in request.hours]
        battery = request.battery.model_dump()

        directives = interpret_notes(request.operator_notes)
        directive_interpretation = [DirectiveInterpretation(**d) for d in directives]

        try:
            result = solve_schedule(hours_data, battery, directives)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        is_valid, violations = validate_final_schedule(
            result["hourly_plan"], hours_data, battery, directives
        )
        totals_violations = validate_totals(
            result["total_grid_kwh"],
            result["total_cost_bdt"],
            result["peak_grid_kwh"],
            result["hourly_plan"],
            hours_data,
        )
        all_violations = violations + totals_violations
        if all_violations:
            logger.warning(
                "validator found %d violation(s) for scenario %s: %s",
                len(all_violations), request.scenario_id, all_violations,
            )

        plan_summary = (
            f"Optimized 24h schedule for '{request.scenario_id}': "
            f"total grid draw {result['total_grid_kwh']:.2f} kWh, "
            f"cost {result['total_cost_bdt']:.2f} BDT, "
            f"peak grid {result['peak_grid_kwh']:.2f} kWh."
        )
        if not is_valid or totals_violations:
            plan_summary += " WARNING: validator flagged issues with this plan; see server logs."

        return OptimizeResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=directive_interpretation,
            hourly_plan=result["hourly_plan"],
            total_grid_kwh=result["total_grid_kwh"],
            total_cost_bdt=result["total_cost_bdt"],
            peak_grid_kwh=result["peak_grid_kwh"],
            plan_summary=plan_summary,
        )
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("unexpected error handling /optimize-energy")
        raise HTTPException(status_code=500, detail="internal server error")
