module lfsr_8bit(input clock,reset,input [7:0] lfsr_seed, output reg [7:0] lfsr_out);
	logic q1,q2,q3;
	//Primitive polynomial considered for 8-bit Linear Feedback Shift Register (LFSR) with Galois configuration is x^8+x^6+x^5+x+1 
	
	//Internal XORing based on primitive polynomial
	assign q1 = lfsr_out[6] ^ lfsr_out[0];
	assign q2 = lfsr_out[5] ^ lfsr_out[0];
	assign q3 = lfsr_out[1] ^ lfsr_out[0];

	always_ff @(posedge clock or negedge reset)
	begin
		if (!reset)
			lfsr_out <= lfsr_seed;//If reset is at logic LOW, the initial seed will be loaded into LFSR's 8-bit output
		else
			lfsr_out <= {lfsr_out[0],lfsr_out[7],q1,q2,lfsr_out[4],lfsr_out[3],lfsr_out[2],q3};//Shift register based on the primitive polynomial
	end
endmodule