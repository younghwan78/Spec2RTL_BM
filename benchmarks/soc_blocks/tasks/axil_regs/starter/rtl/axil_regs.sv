module axil_regs (
  input aclk, input aresetn,
  input [3:0] awaddr, input awvalid, output awready,
  input [31:0] wdata, input [3:0] wstrb, input wvalid, output wready,
  output [1:0] bresp, output bvalid, input bready,
  input [3:0] araddr, input arvalid, output arready,
  output [31:0] rdata, output [1:0] rresp, output rvalid, input rready
);
  // Implement the specified behaviour here.
endmodule
