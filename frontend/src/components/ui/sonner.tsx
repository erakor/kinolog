import { Toaster as Sonner, type ToasterProps } from 'sonner'

/** Light theme only, so no next-themes. Colors come from the Kinolog-mapped shadcn variables. */
function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast: '!rounded-lg !border-primary !bg-primary !text-primary-foreground !text-sm',
          error: '!border-destructive !bg-destructive !text-white',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
