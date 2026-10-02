// Print the disassembly of functions at given addresses.
// Args: <out file> name:hexaddr [name:hexaddr ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpAsm extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(args[0]));
        for (int i = 1; i < args.length; i++) {
            String[] kv = args[i].split(":");
            Address at = toAddr(Long.parseLong(kv[1], 16));
            Function f = getFunctionAt(at);
            if (f == null) {
                disassemble(at);
                f = createFunction(at, kv[0]);
            }
            out.println("; ===== " + kv[0] + " @ " + at);
            if (f == null) {
                continue;
            }
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                out.println(ins.getAddress() + "  " + ins);
            }
        }
        out.close();
    }
}
