module async_fifo #(parameter WIDTH = 8, parameter AW = 3) (
  input wclk, input wrst_n, input wr_en, input [WIDTH-1:0] wdata, output wfull,
  input rclk, input rrst_n, input rd_en, output [WIDTH-1:0] rdata, output rempty
);
  reg [WIDTH-1:0] mem [0:(1<<AW)-1];
  reg [AW:0] wbin, wgray, rbin, rgray, wq1, wq2, rq1, rq2;
  wire [AW:0] wbin_n = wbin + ((wr_en && !wfull) ? 1'b1 : 1'b0);
  wire [AW:0] rbin_n = rbin + (rd_en ? 1'b1 : 1'b0);
  assign wfull = wgray == {~wq2[AW:AW-1], wq2[AW-2:0]};
  assign rempty = rgray == rq2;
  assign rdata = mem[rbin[AW-1:0]];
  always @(posedge wclk or negedge wrst_n)
    if (!wrst_n) begin wbin <= 0; wgray <= 0; wq1 <= 0; wq2 <= 0; end
    else begin
      if (wr_en && !wfull) mem[wbin[AW-1:0]] <= wdata;
      wbin <= wbin_n; wgray <= wbin_n ^ (wbin_n >> 1);
      wq1 <= rgray; wq2 <= wq1;
    end
  always @(posedge rclk or negedge rrst_n)
    if (!rrst_n) begin rbin <= 0; rgray <= 0; rq1 <= 0; rq2 <= 0; end
    else begin
      rbin <= rbin_n; rgray <= rbin_n ^ (rbin_n >> 1);
      rq1 <= wgray; rq2 <= rq1;
    end
endmodule
