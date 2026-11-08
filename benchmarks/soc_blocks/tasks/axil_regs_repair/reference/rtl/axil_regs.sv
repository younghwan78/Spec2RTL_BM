module axil_regs (
  input aclk, input aresetn,
  input [3:0] awaddr, input awvalid, output awready,
  input [31:0] wdata, input [3:0] wstrb, input wvalid, output wready,
  output [1:0] bresp, output bvalid, input bready,
  input [3:0] araddr, input arvalid, output arready,
  output [31:0] rdata, output [1:0] rresp, output rvalid, input rready
);
  reg aw_v, w_v, b_v, r_v;
  reg [1:0] aw_i;
  reg [31:0] w_d, r_d;
  reg [3:0] w_s;
  reg [31:0] regs [0:3];
  integer i;
  assign awready = !aw_v && !b_v;
  assign wready = !w_v && !b_v;
  assign bvalid = b_v;
  assign bresp = 2'b00;
  assign arready = !r_v;
  assign rvalid = r_v;
  assign rdata = r_d;
  assign rresp = 2'b00;
  always @(posedge aclk)
    if (!aresetn) begin
      aw_v <= 0; w_v <= 0; b_v <= 0; r_v <= 0;
      for (i = 0; i < 4; i = i + 1) regs[i] <= 32'b0;
    end else begin
      if (awvalid && awready) begin aw_v <= 1; aw_i <= awaddr[3:2]; end
      if (wvalid && wready) begin w_v <= 1; w_d <= wdata; w_s <= wstrb; end
      if (aw_v && w_v) begin
        for (i = 0; i < 4; i = i + 1) if (w_s[i]) regs[aw_i][8*i +: 8] <= w_d[8*i +: 8];
        aw_v <= 0; w_v <= 0; b_v <= 1;
      end
      if (b_v && bready) b_v <= 0;
      if (arvalid && arready) begin r_v <= 1; r_d <= regs[araddr[3:2]]; end
      if (r_v && rready) r_v <= 0;
    end
endmodule
