//! `#[traced]`: each call of a function, or of every method in an `impl` block, becomes a backend-viz span.
//!
//! `#[traced]` on a function or an inherent `impl` (its `pub` methods but `new`), or a trait `impl` (all its methods).
//! Options: `#[traced(name = "label")]`, `#[traced(redact)]` (no args or results recorded).

use proc_macro::TokenStream;
use proc_macro2::TokenStream as Tokens;
use quote::{ToTokens, quote};
use syn::{
    Block, FnArg, ImplItem, Item, ItemFn, ItemImpl, LitStr, Pat, ReturnType, Signature, Type, Visibility,
    parse_macro_input, parse_quote,
};

#[derive(Default, Clone)]
struct Options {
    name: Option<String>,
    redact: Option<bool>,
}

/// Trace every call: one span with its args, result, time and errors.
#[proc_macro_attribute]
pub fn traced(attr: TokenStream, item: TokenStream) -> TokenStream {
    let mut options = Options::default();
    let parser = syn::meta::parser(|meta| {
        if meta.path.is_ident("redact") {
            options.redact = Some(true);
            Ok(())
        } else if meta.path.is_ident("name") {
            options.name = Some(meta.value()?.parse::<LitStr>()?.value());
            Ok(())
        } else {
            Err(meta.error("traced takes `name = \"…\"` or `redact`"))
        }
    });
    parse_macro_input!(attr with parser);
    match parse_macro_input!(item as Item) {
        Item::Fn(function) => trace_fn(function, &options).into_token_stream().into(),
        Item::Impl(block) => trace_impl(block, &options).into_token_stream().into(),
        other => syn::Error::new_spanned(other, "#[traced] goes on a fn or an impl block").to_compile_error().into(),
    }
}

fn trace_fn(mut function: ItemFn, options: &Options) -> ItemFn {
    function.block = Box::new(traced_block(&function.sig, &function.block, options));
    function
}

fn trace_impl(mut block: ItemImpl, options: &Options) -> ItemImpl {
    let is_trait_impl = block.trait_.is_some();
    for item in &mut block.items {
        let ImplItem::Fn(method) = item else { continue };
        let is_public = !matches!(method.vis, Visibility::Inherited);
        let is_already_traced = method.attrs.iter().any(|attr| attr.path().is_ident("traced"));
        let is_constructor = method.sig.ident == "new"; // like Python's __init__: not traced
        if (is_trait_impl || is_public) && !is_already_traced && !is_constructor && method.sig.constness.is_none() {
            method.block = traced_block(&method.sig, &method.block, options);
        }
    }
    block
}

fn traced_block(sig: &Signature, body: &Block, options: &Options) -> Block {
    let name = options.name.as_ref().map_or_else(|| quote!(None), |name| quote!(Some(#name)));
    let redact = options.redact.map_or_else(|| quote!(None), |redact| quote!(Some(#redact)));
    let records = arg_records(sig);
    let fake_return = fake_return(&sig.output);
    let run = if sig.asyncness.is_some() {
        quote! {
            ::trace::__private::Instrumented::new(__bv_span.clone(), async move { #fake_return #body }).await
        }
    } else {
        quote! { ::trace::__private::in_span(&__bv_span, move || { #fake_return #body }) }
    };
    parse_quote! {{
        #[allow(unused_imports)]
        use ::trace::__private::probes::*;
        fn __bv_here() {}
        let __bv_span = ::trace::__private::start_call(
            #name, file!(), ::std::any::type_name_of_val(&__bv_here), #redact,
        );
        if ::trace::__private::enabled() { #records }
        let __bv_guard = ::trace::__private::CallGuard::new(&__bv_span);
        let __bv_result = #run;
        __bv_guard.finish((&&&&::trace::__private::Probe(&__bv_result)).outcome());
        __bv_result
    }}
}

/// Gives the closure or async block the function's return type, so `?` and `return` inside it infer.
fn fake_return(output: &ReturnType) -> Tokens {
    let ty: Type = match output {
        ReturnType::Default => parse_quote!(()),
        ReturnType::Type(_, ty) if mentions_impl(ty) => return Tokens::new(),
        ReturnType::Type(_, ty) => (**ty).clone(),
    };
    quote! {
        #[allow(unreachable_code, clippy::diverging_sub_expression, clippy::needless_return)]
        if false {
            let __bv_fake: #ty = loop {};
            return __bv_fake;
        }
    }
}

fn mentions_impl(ty: &Type) -> bool {
    ty.to_token_stream().into_iter().any(|token| token.to_string() == "impl")
}

fn arg_records(sig: &Signature) -> Tokens {
    sig.inputs
        .iter()
        .filter_map(|input| match input {
            FnArg::Typed(typed) => match &*typed.pat {
                Pat::Ident(pattern) => Some(arg_record(&pattern.ident)),
                _ => None,
            },
            FnArg::Receiver(_) => None,
        })
        .collect()
}

fn arg_record(ident: &syn::Ident) -> Tokens {
    let name = ident.to_string();
    if is_secret(&name) {
        return quote! { ::trace::__private::record_secret(&__bv_span, #name); };
    }
    let describe = quote! {
        ::trace::__private::record_arg(&__bv_span, #name, &|| (&&::trace::__private::Probe(&#ident)).describe());
    };
    let Some(kind) = data_kind(&name) else { return describe };
    quote! {
        #describe
        ::trace::__private::tag_ids(&__bv_span, #kind, (&&&&::trace::__private::Probe(&#ident)).ids());
    }
}

/// Same words as the Python tracer: pass(word), secret, token, api_key, credential, auth, cookie, session_key.
fn is_secret(name: &str) -> bool {
    let lower = name.to_lowercase();
    ["pass", "secret", "token", "apikey", "api_key", "credential", "auth", "cookie", "session_key"]
        .iter()
        .any(|word| lower.contains(word))
}

/// `source_id` -> `source`, `row_ids` -> `row`, `id` -> `id`; None for other names.
fn data_kind(name: &str) -> Option<String> {
    let is_data = name == "id" || name == "ids" || name.ends_with("_id") || name.ends_with("_ids");
    if !is_data {
        return None;
    }
    let singular = name.strip_suffix('s').unwrap_or(name);
    Some(singular.strip_suffix("_id").unwrap_or(singular).to_owned())
}
