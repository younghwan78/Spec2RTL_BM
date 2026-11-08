module async_fifo #(parameter WIDTH = 8, parameter AW = 3) (
  input wclk, input wrst_n, input wr_en, input [WIDTH-1:0] wdata, output reg wfull,
  input rclk, input rrst_n, input rd_en, output [WIDTH-1:0] rdata, output reg rempty
);
  // Gray pointers registered directly, with registered full and empty flags.
  reg [WIDTH-1:0] mem [0:(1<<AW)-1];
  reg [AW:0] wb, wg, rb, rg, rs1, rs2, ws1, ws2;
  wire [AW:0] wbn = wb + (wr_en & ~wfull), rbn = rb + (rd_en & ~rempty);
  wire [AW:0] wgn = (wbn >> 1) ^ wbn, rgn = (rbn >> 1) ^ rbn;
  assign rdata = mem[rb[AW-1:0]];
  always @(posedge wclk or negedge wrst_n)
    if (!wrst_n) begin wb <= 0; wg <= 0; rs1 <= 0; rs2 <= 0; wfull <= 0; end
    else begin
      if (wr_en & ~wfull) mem[wb[AW-1:0]] <= wdata;
      wb <= wbn; wg <= wgn; rs1 <= rg; rs2 <= rs1;
      wfull <= wgn == {~rs2[AW:AW-1], rs2[AW-2:0]};
    end
  always @(posedge rclk or negedge rrst_n)
    if (!rrst_n) begin rb <= 0; rg <= 0; ws1 <= 0; ws2 <= 0; rempty <= 1; end
    else begin
      rb <= rbn; rg <= rgn; ws1 <= wg; ws2 <= ws1;
      rempty <= rgn == ws2;
    end
endmodule
