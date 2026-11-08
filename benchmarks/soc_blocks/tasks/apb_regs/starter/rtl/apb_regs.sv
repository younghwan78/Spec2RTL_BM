module apb_regs (
  input pclk, input presetn,
  input psel, input penable, input pwrite, input [7:0] paddr, input [31:0] pwdata,
  output [31:0] prdata, output pready, output pslverr,
  input [15:0] status_in, input [7:0] irq_set,
  output [7:0] ctrl, output [7:0] irq_pending
);
  // Implement the specified behaviour here.
endmodule
