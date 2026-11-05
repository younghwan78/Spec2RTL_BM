module saturating_add(input [7:0] a,b, output [7:0] y, output overflow);
wire [8:0] s={1'b0,a}+{1'b0,b}; assign overflow=s[8]; assign y=s[7:0];
endmodule
