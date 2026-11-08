module crc32_byte (
  input clk, input rst,
  input init, input en, input [7:0] data,
  output [31:0] crc
);
  reg [31:0] s;
  function [31:0] next(input [31:0] c, input [7:0] d);
    integer i;
    begin
      next = c ^ {24'b0, d};
      for (i = 0; i < 8; i = i + 1) next = next[0] ? (next >> 1) ^ 32'hEDB88320 : next >> 1;
    end
  endfunction
  assign crc = s;
  always @(posedge clk)
    if (rst || init) s <= 32'hFFFFFFFF;
    else if (en) s <= next(s, data);
endmodule
