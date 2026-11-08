module async_fifo #(parameter WIDTH = 8, parameter AW = 3) (
  input wclk, input wrst_n, input wr_en, input [WIDTH-1:0] wdata, output wfull,
  input rclk, input rrst_n, input rd_en, output [WIDTH-1:0] rdata, output rempty
);
  // Implement the specified behaviour here.
endmodule
