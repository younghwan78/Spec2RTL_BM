module priority_encoder(input [7:0] req, output reg [2:0] index, output valid);
integer k; assign valid=|req; always @* begin index=0; for(k=7;k>=0;k=k-1) if(req[k]) index=k; end
endmodule
