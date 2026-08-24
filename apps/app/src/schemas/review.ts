import * as z from 'zod';

import { nonEmptyStringSchema } from './common';

// Form-only schemas -- validate the reviewer's input before it becomes the
// approve/reject request body in @/api/review.ts.
export const approveFormSchema = z.object({
  reviewed_by: nonEmptyStringSchema,
});
export type ApproveFormValues = z.infer<typeof approveFormSchema>;

export const rejectFormSchema = z.object({
  reviewed_by: nonEmptyStringSchema,
  reason: z.string().optional(),
});
export type RejectFormValues = z.infer<typeof rejectFormSchema>;
