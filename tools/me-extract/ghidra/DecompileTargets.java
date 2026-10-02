// Decompile functions at given addresses, following direct calls a few levels deep.
// Args: <out file> <depth> name:hexaddr [name:hexaddr ...]
// Works without auto-analysis: disassembles and creates each function on demand.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Set;

public class DecompileTargets extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(args[0]));
        int depth = Integer.parseInt(args[1]);
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        Set<Address> done = new HashSet<>();
        ArrayDeque<Object[]> queue = new ArrayDeque<>();
        for (int i = 2; i < args.length; i++) {
            String[] kv = args[i].split(":");
            queue.add(new Object[] { kv[0], toAddr(Long.parseLong(kv[1], 16)), 0 });
        }
        while (!queue.isEmpty()) {
            Object[] item = queue.poll();
            String name = (String) item[0];
            Address at = (Address) item[1];
            int d = (Integer) item[2];
            if (!done.add(at)) {
                continue;
            }
            Function f = getFunctionAt(at);
            if (f == null) {
                disassemble(at);
                f = createFunction(at, name.startsWith("FUN_") ? null : name);
            }
            if (f == null) {
                out.println("// could not create a function at " + at);
                continue;
            }
            DecompileResults r = di.decompileFunction(f, 180, monitor);
            out.println("// ===== " + name + " @ " + at + " (depth " + d + ")");
            out.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// failed: " + r.getErrorMessage());
            if (d < depth) {
                InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    if (!ins.getFlowType().isCall()) {
                        continue;
                    }
                    for (Address target : ins.getFlows()) {
                        queue.add(new Object[] { "FUN_" + target, target, d + 1 });
                    }
                }
            }
        }
        out.close();
        di.dispose();
    }
}
