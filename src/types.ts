export type Message = {
  id: string;
  role: "assistant" | "user" | "system";
  content: string;
  ts?: string;
  tool_result?: any;
  status?: "pending" | "approved" | string;
  meta?: Record<string, any> | undefined;
};


export type Thread = {
  id: string;
  title: string;
  active: boolean;
  insuranceStatus?: 'pending' | 'approved' | 'denied' | null;
  transient?: boolean; // not persisted; hidden from Recents until first user prompt
};


export type ParsedProcedure = { name: string; units?: number; price: number; discount?: number; total?: number };
export type ParsedInvoice = {
draft: {
patient: { full_name?: string; ssn?: string; dob?: string | null };
hospital?: string;
date_of_service?: string | null;
diagnosis?: string[];
procedures?: ParsedProcedure[];
totals?: { subtotal?: number | null; discount?: number | null; tax?: number | null; total?: number | null };
ready_for_insurance?: boolean;
};
missing: string[];
};
