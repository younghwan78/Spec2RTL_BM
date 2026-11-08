Consider the following adder-subtractor with a zero flag:

  module TopModule (
      input      cpu_overheated,
      output reg shut_off_computer,
      input      arrived,
      input      gas_tank_empty,
      output reg keep_driving
  );

      always @(*) begin
          if (cpu_overheated)
             shut_off_computer = 1;
      end

      always @(*) begin
          if (~arrived)
             keep_driving = ~gas_tank_empty;
      end

  endmodule

Unfortunately, this module has a bug. Implement a new version of this
module that fixes the bug.

The module must be named `TopModule`. Provide synthesizable SystemVerilog only; no testbench or simulation system tasks belong in the submitted RTL.


The RTL file provided in this workspace was written for the specification above but contains a functional defect. Repair it so that it fully meets the specification. Keep the module name and ports. Do not rewrite unrelated logic.
