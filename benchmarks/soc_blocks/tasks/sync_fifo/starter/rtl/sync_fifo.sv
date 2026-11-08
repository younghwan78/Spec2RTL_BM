module sync_fifo #(parameter WIDTH = 8, parameter DEPTH = 4) (
  input clk, input rst,
  input wr_en, input [WIDTH-1:0] wr_data, output full,
  input rd_en, output [WIDTH-1:0] rd_data, output empty,
  output [$clog2(DEPTH+1)-1:0] count
);
  // Implement the specified behaviour here.
endmodule
