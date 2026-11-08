module axil_regs (
  input aclk, input aresetn,
  input [3:0] awaddr, input awvalid, output awready,
  input [31:0] wdata, input [3:0] wstrb, input wvalid, output wready,
  output [1:0] bresp, output bvalid, input bready,
  input [3:0] araddr, input arvalid, output arready,
  output [31:0] rdata, output [1:0] rresp, output rvalid, input rready
);
  // Waits for both write channels, then accepts them together in one cycle.
  reg [31:0] r0, r1, r2, r3, rd_q;
  reg bv, rv;
  wire accept = awvalid && wvalid && !bv;
  assign awready = accept;
  assign wready = accept;
  assign bvalid = bv; assign bresp = 0;
  assign arready = arvalid && !rv;
  assign rvalid = rv; assign rdata = rd_q; assign rresp = 0;
  function [31:0] merge(input [31:0] o, input [31:0] n, input [3:0] s);
    merge = {s[3] ? n[31:24] : o[31:24], s[2] ? n[23:16] : o[23:16], s[1] ? n[15:8] : o[15:8], s[0] ? n[7:0] : o[7:0]};
  endfunction
  always @(posedge aclk)
    if (!aresetn) begin r0 <= 0; r1 <= 0; r2 <= 0; r3 <= 0; bv <= 0; rv <= 0; end
    else begin
      if (accept) begin
        bv <= 1;
        case (awaddr[3:2])
          0: r0 <= merge(r0, wdata, wstrb);
          1: r1 <= merge(r1, wdata, wstrb);
          2: r2 <= merge(r2, wdata, wstrb);
          3: r3 <= merge(r3, wdata, wstrb);
        endcase
      end else if (bready) bv <= 0;
      if (arready) begin
        rv <= 1;
        case (araddr[3:2]) 0: rd_q <= r0; 1: rd_q <= r1; 2: rd_q <= r2; 3: rd_q <= r3; endcase
      end else if (rready) rv <= 0;
    end
endmodule
