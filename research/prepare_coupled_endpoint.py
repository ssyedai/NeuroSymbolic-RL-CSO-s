"""Build a separate SWMM candidate with a coupled regulator endpoint solve.

The existing experimental engine linearises each weir/orifice contribution only
on the diagonal of the nodal continuity update and omits conduit flow
sensitivities from ordinary nodes.  That is a Jacobi approximation: the equal
and opposite sensitivity at the other endpoint is omitted.  This generator
retains the same constitutive laws and Picard iteration, but solves the
connected ordinary-node Newton correction as one small dense linear system.
It never replaces the installed SWMM library.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


GLOBAL_STORAGE = """
// Signed raw-flow derivatives for the two endpoints of each regulator.
// Dense workspace is bounded by the model's node count and reused each step.
static double *RegDq1 = NULL, *RegDq2 = NULL, *DepthBeforeSolve = NULL;
static double *CoupledMatrix = NULL, *CoupledRhs = NULL;
static int *CoupledMap = NULL;
"""


DERIVATIVE_FUNCTION = r"""
// Evaluate the signed two-endpoint Jacobian of the unchanged regulator law.
// link_getInflow mutates link work fields; the base evaluation immediately
// following this function restores them before the flow is used.
static void addRegulatorDerivatives(int link)
{
    int side, node;
    double saved, lo, hi, qlo, qhi, derivative, outgoingSlope;
    const double epsilon = 1.0e-7;
    RegDq1[link] = 0.0;
    RegDq2[link] = 0.0;
    for (side = 0; side < 2; side++)
    {
        node = (side == 0) ? Link[link].node1 : Link[link].node2;
        if (Node[node].type == OUTFALL) continue;
        saved = Node[node].newDepth;
        lo = MAX(0.0, saved - epsilon);
        hi = saved + epsilon;
        Node[node].newDepth = lo;
        qlo = link_getInflow(link);
        Node[node].newDepth = hi;
        qhi = link_getInflow(link);
        Node[node].newDepth = saved;
        derivative = (qhi - qlo) / (hi - lo);
        if (!isfinite(derivative)) derivative = 0.0;
        if (side == 0) RegDq1[link] = derivative;
        else RegDq2[link] = derivative;
        outgoingSlope = (side == 0) ? derivative : -derivative;
        if (outgoingSlope > 0.0) Xnode[node].weirSlope += outgoingSlope;
    }
}

"""


COUPLED_SOLVER = r"""
static int ordinaryCoupledNode(int node, double depth)
{
    int canPond, isPonded, isSurcharged = FALSE;
    double crown;
    if (Node[node].type == OUTFALL) return FALSE;
    canPond = AllowPonding && Node[node].pondedArea > 0.0;
    isPonded = canPond && depth > Node[node].fullDepth;
    if (isPonded) return FALSE;
    if (SurchargeMethod == EXTRAN)
    {
        crown = Node[node].crownElev - Node[node].invertElev;
        if (Node[node].type == STORAGE)
            isSurcharged = Node[node].surDepth > 0.0 && depth > Node[node].fullDepth;
        else isSurcharged = crown > 0.0 && depth > crown;
    }
    return !isSurcharged;
}

// In-place Gaussian elimination with scaled partial pivoting.  The system is
// small (only ordinary nodes adjoining weirs/orifices) and diagonally anchored
// by positive nodal surface areas.
static int solveCoupledSystem(int count)
{
    int i, j, k, pivot;
    double largest, value, factor, swap;
    for (k = 0; k < count; k++)
    {
        pivot = k;
        largest = fabs(CoupledMatrix[k*count+k]);
        for (i = k+1; i < count; i++)
        {
            value = fabs(CoupledMatrix[i*count+k]);
            if (value > largest) { largest = value; pivot = i; }
        }
        if (!(largest > 1.0e-12) || !isfinite(largest)) return FALSE;
        if (pivot != k)
        {
            for (j = k; j < count; j++)
            {
                swap = CoupledMatrix[k*count+j];
                CoupledMatrix[k*count+j] = CoupledMatrix[pivot*count+j];
                CoupledMatrix[pivot*count+j] = swap;
            }
            swap = CoupledRhs[k]; CoupledRhs[k] = CoupledRhs[pivot]; CoupledRhs[pivot] = swap;
        }
        for (i = k+1; i < count; i++)
        {
            factor = CoupledMatrix[i*count+k] / CoupledMatrix[k*count+k];
            CoupledMatrix[i*count+k] = 0.0;
            for (j = k+1; j < count; j++)
                CoupledMatrix[i*count+j] -= factor * CoupledMatrix[k*count+j];
            CoupledRhs[i] -= factor * CoupledRhs[k];
        }
    }
    for (i = count-1; i >= 0; i--)
    {
        value = CoupledRhs[i];
        for (j = i+1; j < count; j++) value -= CoupledMatrix[i*count+j] * CoupledRhs[j];
        CoupledRhs[i] = value / CoupledMatrix[i*count+i];
        if (!isfinite(CoupledRhs[i])) return FALSE;
    }
    return TRUE;
}

static void applyCoupledEndpointCorrection(double dt)
{
    int i, j, n1, n2, r1, r2, count = 0;
    double area, dQ, dV, alpha, damping, candidate, yMax, derivative1, derivative2;

    for (i = 0; i < Nobjects[NODE]; i++) CoupledMap[i] = -1;
    // Only hydraulically connected ordinary nodes belong in the block.  Nodes in
    // flooding, ponding or EXTRAN surcharge branches keep the stock update.
    for (j = 0; j < Nobjects[LINK]; j++)
    {
        if (!isTrueConduit(j) && Link[j].type != WEIR && Link[j].type != ORIFICE) continue;
        n1 = Link[j].node1; n2 = Link[j].node2;
        if (ordinaryCoupledNode(n1, DepthBeforeSolve[n1]) &&
            Node[n1].newDepth > 0.0 && Node[n1].newDepth < Node[n1].fullDepth + Node[n1].surDepth &&
            CoupledMap[n1] < 0) CoupledMap[n1] = count++;
        if (ordinaryCoupledNode(n2, DepthBeforeSolve[n2]) &&
            Node[n2].newDepth > 0.0 && Node[n2].newDepth < Node[n2].fullDepth + Node[n2].surDepth &&
            CoupledMap[n2] < 0) CoupledMap[n2] = count++;
    }
    if (count == 0) return;
    memset(CoupledMatrix, 0, count*count*sizeof(double));
    memset(CoupledRhs, 0, count*sizeof(double));

    for (i = 0; i < Nobjects[NODE]; i++)
    {
        r1 = CoupledMap[i];
        if (r1 < 0) continue;
        area = MAX(Xnode[i].newSurfArea, MinSurfArea);
        dQ = Node[i].inflow - Node[i].outflow;
        dV = 0.5 * (Node[i].oldNetInflow + dQ) * dt;
        CoupledMatrix[r1*count+r1] = area;
        CoupledRhs[r1] = -(nodeBalanceIncrement(i, Node[i].oldDepth,
            DepthBeforeSolve[i], DepthBeforeSolve[i], area) - dV);
    }

    alpha = 0.5 * dt * ((Steps > 0) ? Omega : 1.0);
    for (j = 0; j < Nobjects[LINK]; j++)
    {
        if (!isTrueConduit(j) && Link[j].type != WEIR && Link[j].type != ORIFICE) continue;
        n1 = Link[j].node1; n2 = Link[j].node2;
        r1 = CoupledMap[n1]; r2 = CoupledMap[n2];
        if (isTrueConduit(j))
        {
            // dwflow computes the raw momentum-equation derivative including
            // barrels; its two head derivatives are equal and opposite.
            derivative1 = Link[j].dqdh;
            derivative2 = -Link[j].dqdh;
        }
        else
        {
            derivative1 = RegDq1[j];
            derivative2 = RegDq2[j];
        }
        if (r1 >= 0)
        {
            CoupledMatrix[r1*count+r1] += alpha * derivative1;
            if (r2 >= 0) CoupledMatrix[r1*count+r2] += alpha * derivative2;
        }
        if (r2 >= 0)
        {
            if (r1 >= 0) CoupledMatrix[r2*count+r1] -= alpha * derivative1;
            CoupledMatrix[r2*count+r2] -= alpha * derivative2;
        }
    }
    if (!solveCoupledSystem(count)) return;

    // A fixed damped-Newton step retains the established Picard stabilization;
    // it is not fitted to an event or selected from the CSO result.
    damping = (Steps > 0) ? Omega : 1.0;
    // Fail closed for the whole block if a linearised proposal crosses a
    // branch boundary.  Mixed branch solves would not represent one Jacobian.
    for (i = 0; i < Nobjects[NODE]; i++)
    {
        r1 = CoupledMap[i];
        if (r1 < 0) continue;
        candidate = DepthBeforeSolve[i] + damping * CoupledRhs[r1];
        yMax = Node[i].fullDepth + ((!AllowPonding || Node[i].pondedArea <= 0.0) ? Node[i].surDepth : 0.0);
        if (!isfinite(candidate) || candidate <= 0.0 || candidate >= yMax) return;
    }
    for (i = 0; i < Nobjects[NODE]; i++)
    {
        r1 = CoupledMap[i];
        if (r1 < 0) continue;
        candidate = DepthBeforeSolve[i] + damping * CoupledRhs[r1];
        Node[i].newDepth = candidate;
        Node[i].newVolume = node_getVolume(i, candidate);
        Xnode[i].dYdT = fabs(candidate - Node[i].oldDepth) / dt;
        area = MAX(Xnode[i].newSurfArea, MinSurfArea);
        dQ = Node[i].inflow - Node[i].outflow;
        dV = 0.5 * (Node[i].oldNetInflow + dQ) * dt;
        Xnode[i].continuityResidual = fabs(nodeBalanceIncrement(i, Node[i].oldDepth,
            DepthBeforeSolve[i], candidate, area) - dV);
    }
}

"""


def patch_source(before: str) -> str:
    after = before
    anchor = "static TXnode* Xnode;                  // extended nodal information\n"
    if after.count(anchor) != 1:
        raise ValueError("Unexpected shared-state anchor")
    after = after.replace(anchor, anchor + GLOBAL_STORAGE, 1)

    anchor = "static int    findNodeDepths(double dt);\n"
    after = after.replace(
        anchor,
        anchor + "static void   applyCoupledEndpointCorrection(double dt);\n",
        1,
    )

    old = """    Xnode = (TXnode *) calloc(Nobjects[NODE], sizeof(TXnode));
    if ( Xnode == NULL )"""
    new = """    Xnode = (TXnode *) calloc(Nobjects[NODE], sizeof(TXnode));
    RegDq1 = (double *)calloc(Nobjects[LINK], sizeof(double));
    RegDq2 = (double *)calloc(Nobjects[LINK], sizeof(double));
    DepthBeforeSolve = (double *)calloc(Nobjects[NODE], sizeof(double));
    CoupledMatrix = (double *)calloc(Nobjects[NODE] * Nobjects[NODE], sizeof(double));
    CoupledRhs = (double *)calloc(Nobjects[NODE], sizeof(double));
    CoupledMap = (int *)calloc(Nobjects[NODE], sizeof(int));
    if ( Xnode == NULL || RegDq1 == NULL || RegDq2 == NULL || DepthBeforeSolve == NULL ||
         CoupledMatrix == NULL || CoupledRhs == NULL || CoupledMap == NULL )"""
    if after.count(old) != 1:
        raise ValueError("Unexpected allocation anchor")
    after = after.replace(old, new, 1)

    old = "    FREE(Xnode);\n"
    new = """    FREE(CoupledMap);
    FREE(CoupledRhs);
    FREE(CoupledMatrix);
    FREE(DepthBeforeSolve);
    FREE(RegDq2);
    FREE(RegDq1);
    FREE(Xnode);
"""
    if after.count(old) != 1:
        raise ValueError("Unexpected free anchor")
    after = after.replace(old, new, 1)

    start = after.index("// Diagnostic local Jacobian, evaluated serially")
    end = after.index("void findNonConduitFlow", start)
    after = after[:start] + DERIVATIVE_FUNCTION + after[end:]
    old = "if (Link[i].type == WEIR || Link[i].type == ORIFICE) addWeirSlopes(i);"
    new = "if (Link[i].type == WEIR || Link[i].type == ORIFICE) addRegulatorDerivatives(i);"
    if after.count(old) != 1:
        raise ValueError("Unexpected derivative call")
    after = after.replace(old, new, 1)

    old = """    // --- compute new depth for all non-outfall nodes and determine if
    //     depth change from previous iteration is below tolerance
#pragma omp parallel num_threads(NumThreads)
{
    #pragma omp for private(yOld)
    for ( i = 0; i < Nobjects[NODE]; i++ )
    {
        if ( Node[i].type == OUTFALL ) continue;
        yOld = Node[i].newDepth;
        setNodeDepth(i, dt);
        Xnode[i].converged = TRUE;
        if ( fabs(yOld - Node[i].newDepth) > HeadTol )
        {
            Xnode[i].converged = FALSE;
        }
    }
}

   // --- return FALSE if any non-Outfall node failed to converge
    for (i = 0; i < Nobjects[NODE]; i++)
    {
        if ( Node[i].type == OUTFALL ) continue;
        if (Xnode[i].converged == FALSE) return FALSE;
        if (!(Xnode[i].continuityResidual <= 1.0e-6)) return FALSE;
    }"""
    new = """    // --- preserve the common linearisation point for the endpoint block
    for (i = 0; i < Nobjects[NODE]; i++) DepthBeforeSolve[i] = Node[i].newDepth;

    // --- retain the established branch handling as a fail-closed fallback
#pragma omp parallel num_threads(NumThreads)
{
    #pragma omp for
    for ( i = 0; i < Nobjects[NODE]; i++ )
    {
        if ( Node[i].type == OUTFALL ) continue;
        setNodeDepth(i, dt);
    }
}
    applyCoupledEndpointCorrection(dt);

    // --- test convergence only after the coupled correction
    for (i = 0; i < Nobjects[NODE]; i++)
    {
        if ( Node[i].type == OUTFALL ) continue;
        yOld = DepthBeforeSolve[i];
        Xnode[i].converged = fabs(yOld - Node[i].newDepth) <= HeadTol;
        if (Xnode[i].converged == FALSE) return FALSE;
        if (!(Xnode[i].continuityResidual <= 1.0e-6)) return FALSE;
    }"""
    if after.count(old) != 1:
        raise ValueError("Unexpected node-depth loop")
    after = after.replace(old, new, 1)

    anchor = "void setNodeDepth(int i, double dt)\n"
    if after.count(anchor) != 1:
        raise ValueError("Unexpected setNodeDepth anchor")
    after = after.replace(anchor, COUPLED_SOLVER + anchor, 1)
    return after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    before = (args.source / "src/solver/dynwave.c").read_text(encoding="utf-8")
    after = patch_source(before)
    shutil.copytree(args.source, args.out)
    target = args.out / "src/solver/dynwave.c"
    target.write_text(after, encoding="utf-8")
    (args.out / "coupled_endpoint.patch").write_text(
        "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))),
        encoding="utf-8",
    )
    (args.out / "coupled_endpoint_config.json").write_text(
        json.dumps(
            {
                "purpose": "Experimental simultaneous conduit/weir/orifice endpoint Newton correction",
                "source": str(args.source.resolve()),
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
                "unchanged": [
                    "discharge laws",
                    "geometry",
                    "native controls",
                    "routing/head tolerances",
                    "iteration cap",
                ],
                "fallback": "retain established scalar update if block is singular or crosses a branch",
                "production_adoption": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
