module apb_regs (
  input pclk, input presetn,
  input psel, input penable, input pwrite, input [7:0] paddr, input [31:0] pwdata,
  output [31:0] prdata, output pready, output pslverr,
  input [15:0] status_in, input [7:0] irq_set,
  output [7:0] ctrl, output [7:0] irq_pending
);
  reg [7:0] ctrl_q, irq_q;
  reg [31:0] scratch_q, rd;
  wire access = psel && penable;
  wire valid = (paddr[1:0] == 0) && (paddr[7:4] == 0);
  wire irq_wr = access && pwrite && paddr == 8'h08;
  assign pready = 1'b1;
  assign pslverr = access && !valid;
  assign ctrl = ctrl_q;
  assign irq_pending = irq_q;
  always @* case (paddr)
    8'h00: rd = {24'b0, ctrl_q};
    8'h04: rd = {16'b0, status_in};
    8'h08: rd = {24'b0, irq_q};
    8'h0c: rd = scratch_q;
    default: rd = 32'b0;
  endcase
  assign prdata = (access && !pwrite) ? rd : 32'b0;
  always @(posedge pclk)
    if (!presetn) begin ctrl_q <= 0; irq_q <= 0; scratch_q <= 0; end
    else begin
      if (access && pwrite && paddr == 8'h00) ctrl_q <= pwdata[7:0];
      if (access && pwrite && paddr == 8'h0c) scratch_q <= pwdata;
      irq_q <= (irq_q | irq_set) & ~(irq_wr ? pwdata[7:0] : 8'b0);
    end
endmodule
