
module TopModule (
  input clk,
  input d,
  input ar,
  output logic q
);

  always@(posedge clk or posedge ar) begin
    if (ar)
      q <= 1;
    else
      q <= d;
  end

endmodule

